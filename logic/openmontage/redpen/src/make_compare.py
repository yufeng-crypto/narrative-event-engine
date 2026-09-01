# -*- coding: utf-8 -*-
"""生成 case 对照页:原稿 | 实验A(端到端) | 实验B(结构化中介) 并排 + IR 表。"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rp_common import CORPUS, OUT

CASE = sys.argv[1] if len(sys.argv) > 1 else "hair_flow"
SRC_NAME = {"hair_flow": "头发的飘动方向可以配合／对齐处理.jpg"}[CASE]


def b64img(p: Path) -> str:
    ext = p.suffix.lstrip(".").lower().replace("jpg", "jpeg")
    return f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()


def main():
    d = OUT / CASE
    ir_p = d / "ir.json"
    ir = json.loads(ir_p.read_text(encoding="utf-8")) if ir_p.is_file() else {"corrections": []}
    rows = "".join(
        f"<tr><td>{c.get('color','')}</td><td>{c.get('type','')}</td>"
        f"<td>{c.get('transcription','')}</td><td>{c.get('translation','')}</td>"
        f"<td>{c.get('edit_instruction','')}</td></tr>"
        for c in ir.get("corrections", []))
    panels = []
    for title, p in [("原稿(带修正批注)", CORPUS / SRC_NAME),
                     ("实验A:端到端(模型自己读批注)", d / "expA_e2e.png"),
                     ("实验B:结构化中介(VLM解读→IR→执行)", d / "expB_ir.png")]:
        img = f'<img src="{b64img(p)}">' if p.is_file() else "<p>(未生成)</p>"
        panels.append(f"<div class='panel'><h3>{title}</h3>{img}</div>")
    html = f"""<!doctype html><meta charset="utf-8"><title>redpen · {CASE}</title>
<style>body{{font-family:system-ui;margin:16px;background:#fafafa}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
.panel img{{width:100%;border:1px solid #ccc}} h3{{margin:4px 0}}
table{{border-collapse:collapse;margin-top:16px;font-size:13px}}
td,th{{border:1px solid #bbb;padding:4px 8px}}</style>
<h2>redpen 首轮端到端对照 · case: {CASE}</h2>
<div class="grid">{''.join(panels)}</div>
<h3>修正 IR(VLM 解读产物)</h3>
<table><tr><th>颜色</th><th>类型</th><th>原文</th><th>译文</th><th>编辑指令</th></tr>{rows}</table>
"""
    out = d / "compare.html"
    out.write_text(html, encoding="utf-8")
    print("saved:", out)


if __name__ == "__main__":
    main()
