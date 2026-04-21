# -*- coding: utf-8 -*-
"""character_pursuits 冷启动 Phase 0 pipeline。

5 节点链路（见 sandbox_notes/character_pursuits_design_v0.md 节 4）：
  [01] 数据加载（CODE）    -> load_test_data()
  [02] Pursuits 提取（LLM）-> extract_pursuits_v1()
  [03] 规范化 + 去重（CODE）-> normalize_and_dedupe()
  [04] 自检 pass（可选）    -> 跳过（按 D1）
  [05] 写库（CODE）         -> pursuits_store.save()

使用：
  python -m sandbox.tools.pursuits_cold_start \\
      --char-id mengya --user-id test_user
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from sandbox.services import pursuits_store
from sandbox.services.llm import TOOL_KEY_MAP, call_doubao_raw
from sandbox.services.pursuits_v32_adapter import (
    build_new_library_payload,
    parse_injected_library,
)
from sandbox.tools.pursuits_coldstart_probe import (
    COLD_START_PROMPT_V1,
    load_test_data,
)

SANDBOX_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = SANDBOX_ROOT / "sandbox" / "out" / "pursuits_probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------- 维度归一化表 ----------
# LLM 输出里可能出现的各种 dim -> 标准 9 维（家人/社交/工作/兴趣/约定/感情/误会/健康/生活）
DIM_NORMALIZE = {
    "家人": "家人", "家庭": "家人", "亲人": "家人",
    "社交": "社交", "朋友": "社交", "同事": "社交", "邻居": "社交",
    "工作": "工作", "学业": "工作", "事业": "工作", "任务": "工作",
    "兴趣": "兴趣", "个人兴趣": "兴趣", "个人成长": "兴趣",
    "个人技能": "兴趣", "学习": "兴趣", "技能": "兴趣",
    "约定": "约定",
    "感情": "感情", "爱情": "感情", "亲密": "感情",
    "误会": "误会", "隔阂": "误会",
    "健康": "健康", "身材": "健康", "外貌": "健康", "身体": "健康",
    "生活": "生活", "生活习惯": "生活", "环境": "生活",
    "其他": "其他",
}


def normalize_dim(raw: str) -> str:
    if not raw:
        return "其他"
    raw = raw.strip()
    if raw in DIM_NORMALIZE:
        return DIM_NORMALIZE[raw]
    # 模糊匹配
    for key, val in DIM_NORMALIZE.items():
        if key in raw or raw in key:
            return val
    return "其他"


# ---------- title 相似度（用于去重） ----------
def _char_set(s: str) -> set:
    return set(re.sub(r"[\s\W]+", "", s))


def _jaccard(a: str, b: str) -> float:
    sa, sb = _char_set(a), _char_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ---------- [02] LLM 提取 ----------
def extract_pursuits_v1(data: dict) -> list[dict]:
    """跑一次 v1 prompt，返回已解析的 pursuit 数组（未规范化）。"""
    prompt = COLD_START_PROMPT_V1
    for k, v in data.items():
        prompt = prompt.replace("{" + k + "}", v)

    print(f"[cs] prompt chars = {len(prompt)}, calling LLM ...")
    cfg = TOOL_KEY_MAP["doubao-1.5 pro 32k"]
    t0 = time.time()
    raw = call_doubao_raw(
        model=cfg["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=float(cfg["temperature"]),
        max_tokens=6000,
    )
    dt = time.time() - t0
    print(f"[cs] LLM done in {dt:.1f}s, {len(raw)} chars")

    stripped = raw.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    (OUT_DIR / "cold_start_raw.txt").write_text(raw, encoding="utf-8")

    parsed = json.loads(stripped)
    if not isinstance(parsed, list):
        raise ValueError("LLM output 不是 JSON 数组")
    return parsed


# ---------- [03] 规范化 + 去重 ----------
def _make_id(seq: int, when: datetime) -> str:
    return f"pur_{when.strftime('%Y%m%d')}_{seq:03d}"


def _is_usable(p: dict) -> tuple[bool, str]:
    """丢弃不合格条目的判据。返回 (ok, reason)。"""
    title = (p.get("title") or "").strip()
    if not title:
        return False, "missing title"
    if len(title) > 30:
        return False, f"title too long ({len(title)})"

    done = (p.get("done_criterion") or "").strip()
    # v3: done_criterion 在 v1+ 起必填（v3 正式锁 7 字段 schema）
    if not done:
        return False, "missing done_criterion"
    if len(done) < 4:
        return False, "done_criterion too short"
    # 空洞词判据
    VOID = ["一直保持", "持续努力", "好好", "越来越好", "变得更好"]
    if any(w in done for w in VOID) and len(done) < 12:
        return False, f"done_criterion void: {done}"

    # v3: 删除 next_likely_actions 字段；不再做 list 长度校验

    return True, ""


def normalize_and_dedupe(
    raw: list[dict],
    now: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    """规范化 + 去重。返回 (accepted, rejected)，其中 rejected 每项附 _reject_reason。"""
    now = now or datetime.now().astimezone()
    now_iso = now.isoformat(timespec="seconds")

    accepted: list[dict] = []
    rejected: list[dict] = []
    seq = 1

    for i, raw_p in enumerate(raw):
        # 丢弃判据
        ok, reason = _is_usable(raw_p)
        if not ok:
            rej = dict(raw_p)
            rej["_reject_reason"] = reason
            rejected.append(rej)
            continue

        # 与已 accept 的做 title 相似度去重
        # v3: 不再合并 next_likely_actions；只保留 current_stage / done_criterion
        #     字数更长的版本（视为更具体的那条）
        merged = False
        for acc in accepted:
            sim = _jaccard(raw_p["title"], acc["title"])
            if sim >= 0.7:
                if len(raw_p.get("current_stage", "")) > len(acc.get("current_stage", "")):
                    acc["current_stage"] = raw_p["current_stage"]
                if len(raw_p.get("done_criterion", "")) > len(acc.get("done_criterion", "")):
                    acc["done_criterion"] = raw_p["done_criterion"]
                rej = dict(raw_p)
                rej["_reject_reason"] = f"dupe of {acc['id']} (jaccard={sim:.2f})"
                rejected.append(rej)
                merged = True
                break
        if merged:
            continue

        # 规范化
        # v3: 删除 next_likely_actions；只保留 7 业务字段 + 5 元数据 + 2 追踪数组
        p = {
            "id": _make_id(seq, now),
            "title": raw_p["title"].strip(),
            "dimension": normalize_dim(raw_p.get("dimension", "")),
            "current_stage": (raw_p.get("current_stage") or "").strip(),
            "done_criterion": (raw_p.get("done_criterion") or "").strip(),
            "urgency": (raw_p.get("urgency") or "medium").strip(),
            "estimated_span": (raw_p.get("estimated_span") or "持续性").strip(),
            "origin_hint": (raw_p.get("origin_hint") or "").strip(),

            "status": "active",
            "created_at": now_iso,
            "updated_at": now_iso,
            "done_at": None,
            "progress_log": [],
            "linked_schedule_events": [],
        }
        accepted.append(p)
        seq += 1

    return accepted, rejected


# ---------- Pipeline ----------
def run(
    char_id: str,
    user_id: str,
    overwrite: bool = False,
    *,
    pursuits_library_raw: str | None = None,
    return_payload: bool = False,
):
    """Cold Start 主流程。

    两种调用模式：

    1. **Fixture 模式（默认，向后兼容）**：
       `pursuits_library_raw=None` → 用 `pursuits_store.exists/load/save` 读写
       本地 fixture；返回退出码 int（0=ok, 2=已存在 skip）。

    2. **v3.2 注入模式**（模拟 mid-control 调度）：
       `pursuits_library_raw="..." / "" / "null"` → 按 CS-01 if-else 逻辑判断：
       非空 → 直接跳过（CS-END-skip）；空 → 建库。
       若 `return_payload=True`，返回 dict（与 workflow END 输出一致的 new_library
       payload 形状，含 skipped/reason/new_library/accepted_count）。
    """
    # v3.2 注入模式：CS-01 if-else
    if pursuits_library_raw is not None:
        injected_lib = parse_injected_library(pursuits_library_raw, char_id, user_id)
        # 非空库：走 CS-END-skip 分支（CS-01 的 false 分支）
        if injected_lib.get("pursuits"):
            print(f"[cs] library already present in injection for ({char_id}, {user_id}); "
                  f"skip (len(pursuits)={len(injected_lib['pursuits'])})")
            if return_payload:
                return {
                    "skipped": "true",
                    "reason": "library already exists",
                    "accepted_count": 0,
                }
            return 2
        # 空库：落到下面走 LLM 建库路径
        print(f"[cs] injection is empty for ({char_id}, {user_id}); proceed to build")
    else:
        if pursuits_store.exists(char_id, user_id) and not overwrite:
            print(f"[cs] library already exists for ({char_id}, {user_id}); use --overwrite to redo")
            return 2

    # [01]
    print("[cs] [01] loading data ...")
    data = load_test_data()

    # [02]
    print("[cs] [02] LLM extract ...")
    raw = extract_pursuits_v1(data)
    print(f"[cs] LLM returned {len(raw)} raw pursuits")

    # [03]
    print("[cs] [03] normalize + dedupe ...")
    accepted, rejected = normalize_and_dedupe(raw)
    print(f"[cs] accepted: {len(accepted)} | rejected: {len(rejected)}")
    if rejected:
        print("[cs] --- rejected reasons ---")
        for r in rejected:
            print(f"  - '{r.get('title', '?')}' -> {r['_reject_reason']}")

    # [05]
    print("[cs] [05] write library ...")
    lib = pursuits_store.new_library(char_id, user_id, accepted)
    # 在 v3.2 注入模式下仍然写一份本地 fixture（方便 MA/MB e2e 继续用），
    # 但真正要回传 mid-control 的是 new_library payload。
    p = pursuits_store.save(lib)
    print(f"[cs] saved -> {p}")

    # 落一份诊断产物
    diag = {
        "char_id": char_id,
        "user_id": user_id,
        "raw_count": len(raw),
        "accepted_count": len(accepted),
        "rejected": rejected,
    }
    (OUT_DIR / f"cold_start_diag_{char_id}_{user_id}.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 人肉 review 用 readable
    lines = [
        f"char: {char_id} | user: {user_id}",
        f"accepted: {len(accepted)} | rejected: {len(rejected)} | raw: {len(raw)}",
        "",
    ]
    from collections import Counter
    dims = Counter(p["dimension"] for p in accepted)
    urgs = Counter(p["urgency"] for p in accepted)
    spans = Counter(p["estimated_span"] for p in accepted)
    lines.append(f"dims: {dict(dims)}")
    lines.append(f"urg:  {dict(urgs)}")
    lines.append(f"span: {dict(spans)}")
    lines.append("")
    for p in accepted:
        lines.append(
            f"--- {p['id']} [{p['dimension']}/{p['urgency']}/{p['estimated_span']}] ---"
        )
        lines.append(f"  title:  {p['title']}")
        lines.append(f"  stage:  {p['current_stage']}")
        lines.append(f"  done:   {p['done_criterion']}")
        lines.append(f"  origin: {p['origin_hint']}")
    (OUT_DIR / f"cold_start_readable_{char_id}_{user_id}.txt").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"[cs] readable -> {OUT_DIR / f'cold_start_readable_{char_id}_{user_id}.txt'}")

    # v3.2 注入模式：返回 CS-END-ok payload（形状与 workflow END 输出一致）
    if return_payload:
        return {
            "new_library": build_new_library_payload(lib),
            "accepted_count": len(accepted),
        }
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--char-id", default="mengya")
    ap.add_argument("--user-id", default="test_user")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    return run(args.char_id, args.user_id, overwrite=args.overwrite)


if __name__ == "__main__":
    sys.exit(main())
