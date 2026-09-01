# -*- coding: utf-8 -*-
"""redpen worker · 红笔修正 agent MVP

带修正批注的线稿 → 解读(可插拔 VLM,两轮:解读+对图审校) → 修正IR → 编译执行(images.edit)
→ 修正后线稿 + 对照页 + run 账本。

用法:
  python redpen_worker.py <sheet.jpg> [--vlm openai:gpt-4o] [--ir gold.json] [--no-exec]

  --vlm   解读后端 "provider:model"。provider ∈ PROVIDERS(OpenAI 兼容端点)。
  --ir    跳过 VLM,注入外部修正IR(人工金标准/其他模型产物)= WoZ 模式。
  --no-exec 只解读不出图(便宜地批量跑语料)。

模型无关性:解读契约全部在 prompts/*.md 里,任何能看图、能出 JSON 的 LLM 都能按同一契约
接入;执行端(gpt-image-2)与解读端解耦。
"""
import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # worker/
ROOT = HERE.parent                               # redpen/
sys.path.insert(0, str(ROOT / "src"))
from rp_common import OUT, image_edit, openai_key  # noqa: E402

PROMPTS = {p.stem: (HERE / "prompts" / f"{p.stem}.md").read_text(encoding="utf-8")
           for p in (HERE / "prompts").glob("*.md")}

# OpenAI 兼容端点注册表:key_env 存环境变量名,不内联明文(同 forge 蓝图 §11)
PROVIDERS = {
    "openai": {"base_url": None, "key_env": "OPENAI_API_KEY", "default": "gpt-4o"},
    "qwen":   {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
               "key_env": "DASHSCOPE_API_KEY", "default": "qwen-vl-max"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "key_env": "GOOGLE_API_KEY", "default": "gemini-2.5-pro"},
    "xai":    {"base_url": "https://api.x.ai/v1", "key_env": "XAI_API_KEY",
               "default": "grok-4"},
    # 豆包/火山方舟(forge 2026-07-17 实测 vision 判别力 8/8);默认给较强的复核档
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3",
               "key_env": "DOUBAO_API_KEY", "default": "doubao-seed-1-6-251015"},
    # deepseek 视觉实验档(⚠每图压缩上限384 token,细小手写字可能读不清——实测为准)
    "deepseek": {"base_url": "https://api.deepseek.com",
                 "key_env": "DEEPSEEK_API_KEY", "default": "deepseek-v4-flash-vision-exp"},
}

_ENV_FILES = [ROOT.parent / "OpenMontage" / ".env",
              ROOT.parent / "OpenMontage" / "forge" / ".env", ROOT.parent / ".env"]


def _key(env_name: str) -> str:
    import os
    v = os.environ.get(env_name, "")
    if v:
        return v
    for f in _ENV_FILES:
        if not f.is_file():
            continue
        for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.strip().startswith(env_name + "="):
                v = ln.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    raise RuntimeError(f"未取到 {env_name}(env 或 .env)")


def vlm_client(provider: str):
    import httpx
    from openai import OpenAI
    p = PROVIDERS[provider]
    key = openai_key() if p["key_env"] == "OPENAI_API_KEY" else _key(p["key_env"])
    kw = dict(api_key=key, max_retries=3,
              timeout=httpx.Timeout(connect=60.0, read=600.0, write=600.0, pool=600.0))
    if p["base_url"]:
        kw["base_url"] = p["base_url"]
    return OpenAI(**kw)


def stroke_crops(sheet: Path, out_dir: Path, max_crops: int = 4) -> list:
    """彩色笔触簇定位→原分辨率裁片。破解 VLM 输入压缩(如 deepseek 384 token/图)读不清
    细小手写批注的问题:全图给上下文,裁片给细节。纯色彩启发式,漏掉铅笔字是已知局限。"""
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(sheet).convert("RGB")).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mask = (((r - g > 40) & (r - b > 40) & (r > 100)) |          # 红/橙
            ((g - r > 25) & (g - b > 25) & (g > 90)))            # 绿/黄绿
    h, w = mask.shape
    mask[: int(h * 0.12), :] = False                             # 顶部定位孔色块
    cell = 48                                                     # 粗网格聚类,零依赖
    gh, gw = (h + cell - 1) // cell, (w + cell - 1) // cell
    grid = np.zeros((gh, gw), bool)
    ys, xs = np.nonzero(mask)
    grid[ys // cell, xs // cell] = True
    seen, boxes = np.zeros_like(grid), []
    for gy, gx in zip(*np.nonzero(grid)):
        if seen[gy, gx]:
            continue
        stack, cells = [(gy, gx)], []
        seen[gy, gx] = True
        while stack:
            cy, cx = stack.pop()
            cells.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(cells) < 2:                                        # 孤点=色トレス小标记,跳过
            continue
        ys2 = [c[0] for c in cells]; xs2 = [c[1] for c in cells]
        boxes.append((min(xs2) * cell, min(ys2) * cell,
                      min((max(xs2) + 1) * cell, w), min((max(ys2) + 1) * cell, h),
                      len(cells)))
    boxes.sort(key=lambda t: -t[4])
    img = Image.open(sheet).convert("RGB")
    pad, paths = 60, []
    for i, (x0, y0, x1, y1, _) in enumerate(boxes[:max_crops]):
        crop = img.crop((max(0, x0 - pad), max(0, y0 - pad),
                         min(w, x1 + pad), min(h, y1 + pad)))
        p = out_dir / f"crop_{i}.jpg"
        crop.save(p, quality=92)
        paths.append(p)
    return paths


def _extract_json(text: str) -> dict:
    """兼容不支持 response_format 的端点:剥 markdown 围栏后取最外层 {...}。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"VLM 回复中未找到 JSON:{text[:200]}")
    return json.loads(m.group(0))


def vlm_see(cli, model: str, prompt: str, img_b64: str, extra_text: str = "",
            crop_b64s: list | None = None) -> dict:
    content = [{"type": "text", "text": prompt}]
    if extra_text:
        content.append({"type": "text", "text": extra_text})
    content.append({"type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})
    if crop_b64s:
        content.append({"type": "text", "text":
            "The following images are HIGH-RESOLUTION CROPS of the colored annotation "
            "regions from the SAME sheet above, provided so you can read small handwritten "
            "text and stroke details accurately. Use them to transcribe precisely."})
        for cb in crop_b64s:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{cb}"}})
    r = cli.chat.completions.create(model=model,
                                    messages=[{"role": "user", "content": content}])
    return _extract_json(r.choices[0].message.content)


def validate_ir(ir: dict) -> list:
    """schema+接地校验。返回问题清单(空=通过)。接地判据:指令须含具体对象名词,
    纯方位词指令(首轮实验B的失败模式)判不合格——机械近似:去掉方位/几何词后仍须有实词。"""
    problems = []
    if "corrections" not in ir:
        return ["缺 corrections 字段"]
    POSITIONAL = {"left", "right", "top", "bottom", "upper", "lower", "line", "lines",
                  "area", "part", "side", "corner", "region", "mark", "marks", "stroke"}
    for c in ir["corrections"]:
        if not c.get("actionable"):
            continue
        ins = (c.get("edit_instruction") or "").strip()
        if not ins:
            problems.append(f"{c.get('id')}: actionable 但 edit_instruction 为空")
            continue
        words = {w.strip(".,;()").lower() for w in ins.split()}
        content_words = {w for w in words if len(w) > 3 and w not in POSITIONAL
                         and not w.isdigit()}
        if len(content_words) < 2:
            problems.append(f"{c.get('id')}: 指令疑似未绑定对象:{ins!r}")
    return problems


def compile_execute_prompt(ir: dict, bg: str = "light-green paper") -> str:
    lines = []
    n = 0
    for c in ir.get("corrections", []):
        if not c.get("actionable") or not c.get("edit_instruction"):
            continue
        n += 1
        lines.append(f"{n}. {c['edit_instruction'].strip()}")
    if n == 0:
        raise SystemExit("没有可执行修正(actionable=0),不出图。")
    return PROMPTS["execute_template"].replace("{instructions}", "\n".join(lines)) \
                                      .replace("{bg}", bg)


def make_compare(out_dir: Path, src: Path, ir: dict, corrected: Path | None):
    def b64img(p):
        ext = p.suffix.lstrip(".").lower().replace("jpg", "jpeg")
        return f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()
    rows = "".join(
        f"<tr><td>{c.get('color','')}</td><td>{c.get('type','')}</td>"
        f"<td>{'✔' if c.get('actionable') else ''}</td><td>{c.get('location','')}</td>"
        f"<td>{c.get('transcription','')}</td><td>{c.get('edit_instruction','')}</td></tr>"
        for c in ir.get("corrections", []))
    right = (f'<img src="{b64img(corrected)}">' if corrected and corrected.is_file()
             else "<p>(未执行)</p>")
    html = f"""<!doctype html><meta charset="utf-8"><title>redpen · {src.name}</title>
<style>body{{font-family:system-ui;margin:16px}}.g{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
img{{width:100%;border:1px solid #ccc}}table{{border-collapse:collapse;font-size:13px;margin-top:12px}}
td,th{{border:1px solid #bbb;padding:4px 8px}}</style>
<h2>{src.name}</h2><div class="g"><div><h3>原稿</h3><img src="{b64img(src)}"></div>
<div><h3>修正后</h3>{right}</div></div>
<h3>修正 IR</h3><table><tr><th>色</th><th>类型</th><th>可执行</th><th>位置</th><th>原文</th><th>编辑指令</th></tr>{rows}</table>"""
    (out_dir / "compare.html").write_text(html, encoding="utf-8")


def run(sheet: Path, vlm: str, ir_path: Path | None, execute: bool = True) -> Path:
    stem = re.sub(r"[^\w一-鿿]+", "_", sheet.stem)[:40]
    # ⚠ 注入 IR 时标签必须编码**注入源身份**(取 IR 文件父目录名),不许折叠成固定名 ——
    #   固定名会让不同注入源互相覆盖(2026-09-02 实撞:doubao/deepseek 两次注入执行
    #   先后写进 run_gold,把金标准产物顶掉)。同族教训见 openmontage worktree 路径 bug 族:
    #   把"身份"写成"常量"的错,两边都不报错。
    tag = f"ir_{Path(ir_path).parent.name}" if ir_path else vlm.replace(":", "_")
    out_dir = OUT / stem / f"run_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = {"sheet": str(sheet), "vlm": None if ir_path else vlm,
              "ir_injected": str(ir_path) if ir_path else None, "steps": []}
    t0 = time.time()

    if ir_path:                                   # WoZ 模式:外部解读
        ir = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    else:
        provider, _, model = vlm.partition(":")
        model = model or PROVIDERS[provider]["default"]
        cli = vlm_client(provider)
        b64 = base64.b64encode(sheet.read_bytes()).decode()
        crops = stroke_crops(sheet, out_dir)
        crop_b64s = [base64.b64encode(p.read_bytes()).decode() for p in crops]
        ledger["crops"] = [p.name for p in crops]
        print(f"[1/3] interpret via {provider}:{model} (+{len(crops)} crops)", flush=True)
        ir = vlm_see(cli, model, PROMPTS["interpret"], b64, crop_b64s=crop_b64s)
        ledger["steps"].append({"step": "interpret", "sec": round(time.time() - t0, 1)})
        print("[2/3] refine (对图审校)", flush=True)
        ir = vlm_see(cli, model, PROMPTS["refine"], b64,
                     extra_text="Draft JSON:\n" + json.dumps(ir, ensure_ascii=False),
                     crop_b64s=crop_b64s)
        ledger["steps"].append({"step": "refine", "sec": round(time.time() - t0, 1)})

    problems = validate_ir(ir)
    ir["_validation"] = {"passed": not problems, "problems": problems}
    (out_dir / "ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    if problems:
        print("⚠ IR 校验未过(如实入账,不静默放行):", *problems, sep="\n  ")

    corrected = None
    if execute:
        prompt = compile_execute_prompt(ir)
        (out_dir / "execute_prompt.txt").write_text(prompt, encoding="utf-8")
        print("[3/3] execute via gpt-image-2", flush=True)
        corrected = image_edit([sheet], prompt, out_dir / "corrected.png",
                               size="1536x1024")
        ledger["steps"].append({"step": "execute", "sec": round(time.time() - t0, 1)})

    make_compare(out_dir, sheet, ir, corrected)
    ledger["validation"] = ir["_validation"]
    ledger["out_dir"] = str(out_dir)
    (out_dir / "run.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print("done:", out_dir / "compare.html")
    return out_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--vlm", default="openai:gpt-4o")
    ap.add_argument("--ir", default=None)
    ap.add_argument("--no-exec", action="store_true")
    a = ap.parse_args()
    run(Path(a.sheet), a.vlm, Path(a.ir) if a.ir else None, execute=not a.no_exec)
