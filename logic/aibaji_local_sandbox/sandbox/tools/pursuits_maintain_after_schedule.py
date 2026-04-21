# -*- coding: utf-8 -*-
"""character_pursuits 维护工作流 M-B：离线日程生成**后**的 pursuit 状态维护。

参见 sandbox_notes/character_pursuits_design_v0.md 节 5.2。

流水线（单次 LLM 调用）：
  [01] 数据加载（CODE）       -> load_library + load_recent_events
  [02] 构造 prompt（CODE）    -> build_prompt
  [03] LLM 维护判断（LLM）     -> call_llm
  [04] 解析 + 校验（CODE）    -> parse_response
  [05] 应用变更（CODE）       -> apply_changes + rebuild_top5
  [06] 保存 + 产出 readable  -> pursuits_store.save + emit_readable_diff

使用：
  # 用 Phase 1 layer1_2_3 跑出的 11 条事件当测试输入
  python -m sandbox.tools.pursuits_maintain_after_schedule \\
      --char-id mengya --user-id test_user \\
      --events-dir sandbox/out/runs/phase1_mengya_l123/seed_0

输出：
  sandbox/out/pursuits_probe/mb_raw_<char>_<user>.txt
  sandbox/out/pursuits_probe/mb_parsed_<char>_<user>.json
  sandbox/out/pursuits_probe/mb_diff_<char>_<user>.txt
  （并把库对象 save 回 sandbox/fixtures/pursuits/<char>__<user>.json）
"""
from __future__ import annotations

import argparse
import copy
import json
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

SANDBOX_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = SANDBOX_ROOT / "sandbox" / "out" / "pursuits_probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# [01] 数据加载
# ============================================================================

# 规范化事件的字段集（M-B 内部使用）：
#   step          int        事件在本批里的序号，供 LLM 引用（event_refs）
#   id            str        对齐线上 schedule_timeline.id（evt_YYYYMMDD_HHMM_XX）
#   start_dt      str        展示给 LLM 的起点（格式：YYYY-MM-DD HH:MM，北京时）
#   end_dt        str        展示给 LLM 的终点（同上）
#   duration_min  int
#   description   str        线上字段名，等于沙盒 step.json 里的 header.desc
#   location      str
#   summary       str
#   expression    str
#   clothing      str
#   deepthinking  str        线上"心声"字段名（沙盒 step.json 用 heart）
#   reunion_hook  str        线上"重逢钩子"字段名（沙盒 step.json 没有）

_TIMELINE_SCHEMA_FIELDS = (
    "id", "start_time", "end_time", "duration_minutes",
    "description", "location", "summary", "expression",
    "clothing", "deepthinking", "reunion_hook",
)


def _iso_utc_to_bj_display(iso_utc: str) -> str:
    """线上 schedule_timeline 里 start_time/end_time 是 UTC ISO（"2026-04-19T04:01:00Z"）。
    M-B prompt 展示时转成北京时间 "YYYY-MM-DD HH:MM"，方便 LLM 读。
    """
    from datetime import datetime, timedelta, timezone
    if not iso_utc:
        return ""
    s = iso_utc.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt_utc = datetime.fromisoformat(s)
    except ValueError:
        return iso_utc  # 解析失败直接回原值
    dt_bj = dt_utc.astimezone(timezone(timedelta(hours=8)))
    return dt_bj.strftime("%Y-%m-%d %H:%M")


def _events_from_step_dir(events_dir: Path) -> list[dict]:
    """legacy 沙盒路径：从 simulate_full_day.py 的 step_*.json 读事件。"""
    step_files = sorted(events_dir.glob("step_*.json"))
    if not step_files:
        raise FileNotFoundError(f"no step_*.json in {events_dir}")

    events: list[dict] = []
    for sf in step_files:
        step = json.loads(sf.read_text(encoding="utf-8"))
        parsed = (step.get("validator") or {}).get("parsed") or {}
        header = parsed.get("header") or {}
        if not header:
            continue
        events.append({
            "step": step.get("step"),
            "id": None,  # 沙盒 step 产物没有 evt_id
            "start_dt": header.get("start_dt"),
            "end_dt": header.get("end_dt"),
            "duration_min": header.get("duration_min"),
            "description": header.get("desc", ""),
            "location": parsed.get("location", ""),
            "summary": parsed.get("summary", ""),
            "expression": parsed.get("expression", ""),
            "clothing": parsed.get("clothing", ""),
            "deepthinking": parsed.get("heart", ""),
            "reunion_hook": parsed.get("reunion_hook", ""),
        })
    return events


def _parse_schedule_timeline_raw(raw) -> list[dict]:
    """线上 schedule_timeline 可能是：
    - Python list（已 parse）
    - 单层 JSON 字符串
    - 双重编码的 JSON 字符串（Dify END 节点 bug；解两次才是数组）

    见 sandbox_notes/feedback_dify_encoding.md / business_rules_and_patches.md INV-007。
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    try:
        a = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(a, list):
        return a
    if isinstance(a, str):
        # 双重编码兜底
        try:
            b = json.loads(a)
            return b if isinstance(b, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _events_from_timeline_json(timeline_path: Path, since_id: str | None = None) -> list[dict]:
    """从 `schedule_timeline` 缓存（11 字段真 schema）读事件。

    timeline_path 可以是：
    - 直接就是一个 JSON 数组文件
    - 一个 {value: "<双重编码字符串>"} 包装（模拟 Dify 缓存读出来的形态）
    - 一个 {schedule_timeline: "..."} 或 {schedule_timeline: [...]}

    since_id：如果给了 evt_id，只返回时间上严格在它之后的事件（跳过已处理）。
    """
    content = timeline_path.read_text(encoding="utf-8")
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        obj = content  # 可能就是纯 JSON 字符串

    # 从各种外层形态提取真正的 timeline 数组
    raw = obj
    if isinstance(obj, dict):
        for k in ("schedule_timeline", "value", "timeline"):
            if k in obj:
                raw = obj[k]
                break

    arr = _parse_schedule_timeline_raw(raw)
    arr.sort(key=lambda e: str(e.get("start_time", "")))

    events: list[dict] = []
    seen_since = since_id is None
    step = 1
    for ev in arr:
        if not isinstance(ev, dict):
            continue
        if since_id and not seen_since:
            if ev.get("id") == since_id:
                seen_since = True
            continue
        events.append({
            "step": step,
            "id": ev.get("id"),
            "start_dt": _iso_utc_to_bj_display(ev.get("start_time", "")),
            "end_dt": _iso_utc_to_bj_display(ev.get("end_time", "")),
            "duration_min": ev.get("duration_minutes"),
            "description": ev.get("description", ""),
            "location": ev.get("location", ""),
            "summary": ev.get("summary", ""),
            "expression": ev.get("expression", ""),
            "clothing": ev.get("clothing", ""),
            "deepthinking": ev.get("deepthinking", ""),
            "reunion_hook": ev.get("reunion_hook", ""),
        })
        step += 1
    return events


def load_recent_events(
    events_dir: Path | None = None,
    timeline_json: Path | None = None,
    since_id: str | None = None,
) -> list[dict]:
    """规范化入口。二选一：
    - `events_dir`：沙盒 step_*.json 目录（legacy，不含 id/clothing/reunion_hook）
    - `timeline_json`：线上真 schedule_timeline schema（含 11 字段）

    两种路径返回同一套内部字段（见 _TIMELINE_SCHEMA_FIELDS + step）。
    """
    if timeline_json is not None:
        return _events_from_timeline_json(timeline_json, since_id=since_id)
    if events_dir is not None:
        return _events_from_step_dir(events_dir)
    raise ValueError("必须提供 events_dir 或 timeline_json 之一")


# ============================================================================
# [02] 构造 prompt
# ============================================================================

MAINTAIN_PROMPT = """你是一个 AI 伴侣角色的"自驱目标库维护者"。你的任务是：读一批刚刚生成的**未来 24 小时日程事件**，并根据这些事件对角色的 `active pursuits` 库做状态维护。

⚠️ v3 说明：你**只**负责 3 类判断（progress_updates / completed / priority_order）。
   - 不要 to_pause（事件没排≠应该 pause；超期 paused 由 CODE 层算）
   - 不要 to_revive（revive 只该由真实对话里的用户/角色决定，归 MA）
   - 不要 new_pursuits（MB 只面对已生成日程，没有足够情境新建 pursuit）
   - 不要 update_estimated_span / update_done_criterion（修改性字段必须带用户原话，MB 没有）

---

## 输入 A：当前的 active pursuits 清单
{pursuits_block}

---

## 输入 B：刚刚生成的 24 小时日程事件（按时间顺序）
{events_block}

---

## 你要做的 3 件事（输出 JSON 时按此顺序）

### 1) progress_updates：推进了哪些 pursuit？
- 逐条扫描事件。如果事件的 `desc / summary / heart` 明显对应某条 active pursuit，就记录：
  - `pursuit_id`
  - `event_refs`：事件 step 编号数组（可多条事件对同一 pursuit 都有推进）
  - `new_current_stage`：用一句话（≤ 30 字）把 pursuit 的当前阶段更新为"刚做了什么、下一步要做什么"
  - `progress_log_entry`：一句话（≤ 40 字）摘要本次推进内容，会追加到 progress_log
- 如果事件只是日常（吃饭/散步/睡觉）且和任何 pursuit 都不挂钩，**不要强行归因**。

### 2) completed：是否有 pursuit 达到了 done_criterion？
- 对照 `done_criterion` 字段严判。事件内容只是"部分推进"的，**不要**算 completed。
- 输出 `{{"pursuit_id": "...", "reason": "...", "event_refs": [N]}}`（event_refs 指向促成 done 的那条事件）。

### 3) priority_order：下次 P2 应该优先推进的 top-5 pursuit_id 顺序
- 只从 **active**（含本次新标的 progress 更新后仍在 active 的）里挑，**不含** completed/paused/dropped。
- 优先规则：紧迫（hard > medium > soft）→ 短期 span → 剧情连续性（pacing_tag 落在"推进期/收尾期"的更优先）。
- 最多 5 条。不足 5 条就照实给。

---

## 输出格式（严格 JSON，不要外层 markdown 围栏）

```
{{
  "progress_updates": [
    {{"pursuit_id": "pur_...", "event_refs": [4, 5], "new_current_stage": "...", "progress_log_entry": "..."}}
  ],
  "completed": [
    {{"pursuit_id": "pur_...", "reason": "...", "event_refs": [7]}}
  ],
  "priority_order": ["pur_aaa", "pur_bbb", "pur_ccc", "pur_ddd", "pur_eee"]
}}
```

### 硬约束
- 所有 `pursuit_id` 必须来自输入 A。不能编造。
- `event_refs` 里的 step 编号必须来自输入 B。
- 同一个 pursuit_id 不能同时出现在 progress_updates 和 completed 里。
- 只输出 JSON，不要任何解释或 markdown。
- 输出里如果出现 to_pause / to_revive / new_pursuits / update_* 字段，CODE 层会**忽略**（不报错，但也不生效）。
"""


def _fmt_pursuits_block(actives: list[dict]) -> str:
    """把 active pursuits 格式化成 LLM 可读的块。"""
    lines = []
    for i, p in enumerate(actives, 1):
        lines.append(
            f"#{i}  id={p['id']}  [{p.get('dimension','?')}/{p.get('urgency','?')}/{p.get('estimated_span','?')}]"
        )
        lines.append(f"     title: {p.get('title','')}")
        lines.append(f"     stage: {p.get('current_stage','')}")
        lines.append(f"     done:  {p.get('done_criterion','')}")
        plog = p.get("progress_log") or []
        if plog:
            lines.append(f"     progress_log ({len(plog)} entries, 最近 2 条): {plog[-2:]}")
    return "\n".join(lines)


def _fmt_events_block(events: list[dict]) -> str:
    lines = []
    for ev in events:
        head = (
            f"step{ev['step']:02d}  {ev.get('start_dt','')} - {ev.get('end_dt','')} "
            f"({ev.get('duration_min','?')} min) @ {ev.get('location','')}"
        )
        if ev.get("id"):
            head += f"  id={ev['id']}"
        lines.append(head)
        lines.append(f"    desc:    {ev.get('description', '')}")
        lines.append(f"    summary: {ev.get('summary', '')}")
        if ev.get("expression"):
            lines.append(f"    expr:    {ev['expression']}")
        if ev.get("clothing"):
            lines.append(f"    cloth:   {ev['clothing']}")
        lines.append(f"    heart:   {ev.get('deepthinking', '')}")
        if ev.get("reunion_hook"):
            lines.append(f"    hook:    {ev['reunion_hook']}")
    return "\n".join(lines)


def build_prompt(lib: dict, events: list[dict]) -> str:
    actives = [p for p in lib.get("pursuits", []) if p.get("status") == "active"]
    return MAINTAIN_PROMPT.format(
        pursuits_block=_fmt_pursuits_block(actives),
        events_block=_fmt_events_block(events),
    )


# ============================================================================
# [03] LLM 调用
# ============================================================================

def call_llm(prompt: str) -> str:
    cfg = TOOL_KEY_MAP["doubao-1.5 pro 32k"]
    print(f"[mb] prompt chars = {len(prompt)}, calling LLM ...")
    t0 = time.time()
    raw = call_doubao_raw(
        model=cfg["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=float(cfg["temperature"]),
        max_tokens=4000,
    )
    dt = time.time() - t0
    print(f"[mb] LLM done in {dt:.1f}s, {len(raw)} chars")
    return raw


# ============================================================================
# [04] 解析 + 校验
# ============================================================================

class MaintainParseError(ValueError):
    pass


def parse_response(raw: str, lib: dict, events: list[dict]) -> dict:
    """v3：只解析 3 桶（progress_updates / completed / priority_order）。

    - MB 不做 to_pause / to_revive / new_pursuits（见 v3 §0.5）—— 若 LLM 仍输出这些字段，
      它们会被 **silently discarded**（不 raise），并写进 `obj['deprecated_ignored']` 供 review。
    - auto_paused 不由 LLM 决定；apply_changes 之后会在 CODE 层额外扫一遍 active 列表。
    - 结构性错误（JSON 坏 / pursuit_id 不在库 / step 未知 / 桶互斥）依然 raise。
    """
    stripped = raw.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise MaintainParseError(f"LLM output 不是合法 JSON: {e}\nraw head: {stripped[:300]}")

    if not isinstance(obj, dict):
        raise MaintainParseError(f"LLM output 不是 JSON 对象，而是 {type(obj).__name__}")

    # v3：只保留 3 桶，旧 MB 桶若存在则挪到 deprecated_ignored
    deprecated = {}
    for k in ("to_pause", "to_revive", "new_pursuits",
              "update_estimated_span", "update_done_criterion"):
        if k in obj:
            dropped = obj.pop(k)
            if dropped:
                deprecated[k] = dropped
    obj["deprecated_ignored"] = deprecated

    for k in ("progress_updates", "completed", "priority_order"):
        obj.setdefault(k, [])

    # LLM 容错：event_refs 可能被生成成 "step01" / "step 1" / "1" / 1 等五花八门的形式。
    import re as _re
    def _coerce_step(v):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            m = _re.search(r"(\d+)", v)
            if m:
                return int(m.group(1))
        return v  # 保留原值让 validator 报错

    for bucket_name in ("progress_updates", "completed"):
        for it in obj[bucket_name]:
            if isinstance(it, dict) and "event_refs" in it:
                it["event_refs"] = [_coerce_step(x) for x in (it["event_refs"] or [])]

    # 引用完整性校验
    valid_ids = {p["id"] for p in lib.get("pursuits", [])}
    active_ids = {p["id"] for p in lib.get("pursuits", []) if p.get("status") == "active"}
    valid_steps = {ev["step"] for ev in events}

    errors: list[str] = []

    def _check_ids(section_name: str, items: list, id_key: str = "pursuit_id", must_be_active: bool = False):
        for i, it in enumerate(items):
            pid = it.get(id_key) if isinstance(it, dict) else None
            if pid not in valid_ids:
                errors.append(f"{section_name}[{i}].{id_key}={pid!r} 不在库中")
            elif must_be_active and pid not in active_ids:
                errors.append(f"{section_name}[{i}].{id_key}={pid!r} 不是 active，不能操作")

    _check_ids("progress_updates", obj["progress_updates"], must_be_active=True)
    _check_ids("completed",        obj["completed"],        must_be_active=True)

    def _check_step_refs(bucket_name: str):
        for i, it in enumerate(obj[bucket_name]):
            refs = it.get("event_refs") or []
            for r in refs:
                if r not in valid_steps:
                    errors.append(f"{bucket_name}[{i}].event_refs 含未知 step {r}")
    _check_step_refs("progress_updates")
    _check_step_refs("completed")

    for i, pid in enumerate(obj["priority_order"]):
        if pid not in valid_ids:
            errors.append(f"priority_order[{i}]={pid!r} 不在库中")

    # progress_updates 和 completed 冲突
    pu_ids = {it.get("pursuit_id") for it in obj["progress_updates"]}
    cp_ids = {it.get("pursuit_id") for it in obj["completed"]}
    both = pu_ids & cp_ids
    if both:
        errors.append(f"progress_updates 和 completed 冲突: {both}")

    if errors:
        raise MaintainParseError("LLM 输出引用校验失败:\n  - " + "\n  - ".join(errors))

    return obj


# ============================================================================
# [05] 应用变更
# ============================================================================

def _event_ts_iso(ev: dict) -> str | None:
    """取事件的"角色时间"ts：优先 start_time（线上 ISO UTC），fallback 到 start_dt（北京时间展示）。"""
    st = ev.get("start_time")
    if st:
        return st
    sdt = ev.get("start_dt")
    if sdt:
        # "2026-04-21 09:00" 北京时 → 转 ISO UTC 方便后续 character_time 解析
        try:
            from datetime import datetime as _dt, timedelta, timezone
            bj = _dt.strptime(sdt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
            return bj.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            return sdt
    return None


def apply_changes(
    lib: dict,
    decision: dict,
    events: list[dict],
    *,
    schedule_timeline: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """v3：返回**新的** lib 对象（不改 in-place）。

    关键变更：
    - progress_log.ts 优先取 event.start_time（**角色时间**），不是 apply 时的 now_iso
    - 每条 log 带 `by: "MB"` / `event_ref: evt_id`
    - 新增 auto_paused：对每条 active pursuit 用 character_time 判定是否该自动挂起
    - 删除 to_pause / to_revive / new_pursuits 应用逻辑（v3 MB 不再碰）

    `schedule_timeline` 可选；若未提供，auto_paused 将用 events 自身当窗扫描。
    """
    # 延迟 import 避免 character_time 成环
    from sandbox.tools.character_time import should_auto_pause

    new_lib = copy.deepcopy(lib)
    now = now or datetime.now().astimezone()
    now_iso = now.isoformat(timespec="seconds")

    by_id = {p["id"]: p for p in new_lib["pursuits"]}
    ev_by_step = {ev["step"]: ev for ev in events}

    # 供 auto_paused 用的 timeline：优先 caller 传入，否则用 events（作为近似）
    timeline_for_pace: list[dict] = schedule_timeline or []
    if not timeline_for_pace:
        for ev in events:
            st = _event_ts_iso(ev)
            et = ev.get("end_time")
            if not et and ev.get("end_dt"):
                et = _event_ts_iso({"start_dt": ev["end_dt"]})
            if st and et:
                timeline_for_pace.append({
                    "id": ev.get("id"),
                    "start_time": st,
                    "end_time": et,
                    "summary": ev.get("summary"),
                })

    # 1) progress_updates
    for it in decision["progress_updates"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        refs = it.get("event_refs") or []
        # 用"角色时间"：最早 event_ref 的 start_time
        primary_ev = next((ev_by_step.get(r) for r in refs if r in ev_by_step), None)
        log_ts = _event_ts_iso(primary_ev) if primary_ev else now_iso

        new_stage = (it.get("new_current_stage") or "").strip()
        if new_stage:
            p["current_stage"] = new_stage
        entry = {
            "ts": log_ts,
            "source": "schedule",
            "by": "MB",
            "summary": (it.get("progress_log_entry") or "").strip(),
            "event_refs": refs,
        }
        if primary_ev:
            entry["primary_event_id"] = primary_ev.get("id") or primary_ev.get("start_dt")
        p.setdefault("progress_log", []).append(entry)
        # linked_schedule_events 累加：优先用 evt_id（线上稳定引用），
        # 沙盒 step 产物没有 id 时 fallback 到 start_dt 字符串。
        for r in refs:
            ev = ev_by_step.get(r)
            if not ev:
                continue
            ref_key = ev.get("id") or ev.get("start_dt")
            if ref_key and ref_key not in p.get("linked_schedule_events", []):
                p.setdefault("linked_schedule_events", []).append(ref_key)
        p["updated_at"] = now_iso

    # 2) completed
    for it in decision["completed"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        refs = it.get("event_refs") or []
        primary_ev = next((ev_by_step.get(r) for r in refs if r in ev_by_step), None)
        done_ts = _event_ts_iso(primary_ev) if primary_ev else now_iso
        p["status"] = "done"
        p["done_at"] = done_ts
        p["updated_at"] = now_iso
        p.setdefault("progress_log", []).append({
            "ts": done_ts,
            "source": "schedule",
            "by": "MB",
            "summary": "[DONE] " + (it.get("reason") or "").strip(),
            "event_refs": refs,
        })

    # 3) auto_paused 扫描（v3 新增，code-driven；在 progress/completed 之后执行，
    #    这样"刚推进过"的 pursuit 不会误判为 paused）
    auto_paused_ids: list[dict] = []
    for p in new_lib["pursuits"]:
        if p.get("status") != "active":
            continue
        should, c_days = should_auto_pause(p, now, timeline_for_pace)
        if should:
            p["status"] = "paused"
            p["updated_at"] = now_iso
            p.setdefault("progress_log", []).append({
                "ts": now_iso,
                "source": "system",
                "by": "MB.auto_paused",
                "summary": f"[AUTO_PAUSE] 角色时间 {c_days:.1f} 天无推进 (阈值 14)",
                "event_refs": [],
            })
            auto_paused_ids.append({"pursuit_id": p["id"], "char_days_idle": round(c_days, 2)})

    # 4) 重算计数 + 按 priority_order 重建 top-5 快照
    active_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "active")
    done_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "done")
    dropped_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "dropped")
    paused_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "paused")
    new_lib["active_count"] = active_count
    new_lib["done_count"] = done_count
    new_lib["dropped_count"] = dropped_count
    new_lib["paused_count"] = paused_count

    pursuits_store.rebuild_top5_from_order(new_lib, decision["priority_order"])

    new_lib["last_maintenance_at"] = now_iso
    new_lib["_last_mb_auto_paused"] = auto_paused_ids
    return new_lib


# ============================================================================
# [06] 人肉 review
# ============================================================================

def emit_readable_diff(old_lib: dict, new_lib: dict, decision: dict, events: list[dict]) -> str:
    old_by_id = {p["id"]: p for p in old_lib["pursuits"]}
    new_by_id = {p["id"]: p for p in new_lib["pursuits"]}

    lines: list[str] = []
    lines.append("========== M-B 维护结果 diff ==========")
    lines.append(f"char: {new_lib['char_id']} | user: {new_lib['user_id']}")
    lines.append(f"events fed to LLM: {len(events)}")
    lines.append(
        f"active: {old_lib.get('active_count',0)} -> {new_lib.get('active_count',0)}  | "
        f"done: {old_lib.get('done_count',0)} -> {new_lib.get('done_count',0)}  | "
        f"paused: {old_lib.get('paused_count',0)} -> {new_lib.get('paused_count',0)}  | "
        f"dropped: {old_lib.get('dropped_count',0)} -> {new_lib.get('dropped_count',0)}"
    )
    lines.append("")

    # ---------- progress_updates ----------
    lines.append(f"--- [1] progress_updates: {len(decision['progress_updates'])} ---")
    for it in decision["progress_updates"]:
        pid = it["pursuit_id"]
        old_p = old_by_id.get(pid, {})
        new_p = new_by_id.get(pid, {})
        lines.append(f"  {pid}  {new_p.get('title','')}")
        lines.append(f"    event_refs: step{it.get('event_refs', [])}")
        if old_p.get("current_stage") != new_p.get("current_stage"):
            lines.append(f"    stage:  \"{old_p.get('current_stage','')}\"")
            lines.append(f"      -> \"{new_p.get('current_stage','')}\"")
        lines.append(f"    + log: {it.get('progress_log_entry','')}")

    # ---------- completed ----------
    lines.append("")
    lines.append(f"--- [2] completed: {len(decision['completed'])} ---")
    for it in decision["completed"]:
        pid = it["pursuit_id"]
        lines.append(f"  {pid}  {new_by_id.get(pid,{}).get('title','')}")
        lines.append(f"    reason: {it.get('reason','')}")

    # ---------- auto_paused (v3，code-driven) ----------
    auto_paused = new_lib.get("_last_mb_auto_paused", []) or []
    lines.append("")
    lines.append(f"--- [3] auto_paused (code-driven, 阈值 14 角色天): {len(auto_paused)} ---")
    for it in auto_paused:
        pid = it["pursuit_id"]
        lines.append(
            f"  {pid}  {new_by_id.get(pid, {}).get('title','')}"
            f"  idle={it['char_days_idle']} 天"
        )

    # ---------- deprecated_ignored (v3 silently discard) ----------
    dep = decision.get("deprecated_ignored") or {}
    total_dep = sum(len(v) for v in dep.values() if isinstance(v, list))
    lines.append("")
    lines.append(f"--- [4] deprecated_ignored (LLM 多输出的 v2 旧桶，已静默丢弃): {total_dep} ---")
    for k, v in dep.items():
        if isinstance(v, list) and v:
            lines.append(f"  {k}: {len(v)} 条（已忽略）")

    # ---------- priority_order / top-5 cache ----------
    lines.append("")
    lines.append(f"--- [5] new pursuits_top5_cache (order from LLM) ---")
    for i, p in enumerate(new_lib.get("pursuits_top5_cache", []), 1):
        lines.append(f"  {i}. {p.get('id')}  [{p.get('urgency','?')}/{p.get('estimated_span','?')}]  {p.get('title','')}")

    return "\n".join(lines)


# ============================================================================
# Pipeline
# ============================================================================

def run(
    char_id: str,
    user_id: str,
    events_dir: Path | None = None,
    timeline_json: Path | None = None,
    since_id: str | None = None,
    dry_run: bool = False,
    *,
    pursuits_library_raw: str | None = None,
    return_payload: bool = False,
):
    """M-B 主流程。

    两种调用模式（同 CS / MA）：

    1. **Fixture 模式**：`pursuits_library_raw=None` → 读/写本地 fixture；返回 int。
    2. **v3.2 注入模式**：传 `pursuits_library_raw`（字符串 / "" / "null"）→
       绕过本地读；若 `return_payload=True`，返回 MB-END 形状的 dict
       `{new_library, accepted_count, auto_paused_summary}`。

    空库注入时 MB 视作 no-op（只会跑 auto_paused 扫描，但没 active 需要扫）。
    """
    # [01]
    src_desc = f"events_dir={events_dir}" if events_dir else f"timeline_json={timeline_json}"
    print(f"[mb] [01] loading library ({char_id}, {user_id}) and events from {src_desc} ...")
    if pursuits_library_raw is not None:
        lib = parse_injected_library(pursuits_library_raw, char_id, user_id)
        if not lib.get("pursuits"):
            print(f"[mb] WARN: injection is empty for ({char_id}, {user_id}); MB no-op")
            if return_payload:
                return {
                    "new_library": build_new_library_payload(lib),
                    "accepted_count": 0,
                    "auto_paused_summary": "progress=0 completed=0 auto_paused=0",
                }
            return 2
    else:
        lib = pursuits_store.load(char_id, user_id)
        if lib is None:
            print(f"[mb] ERROR: library not found for ({char_id}, {user_id}); run pursuits_cold_start first")
            return 2
    events = load_recent_events(events_dir=events_dir, timeline_json=timeline_json, since_id=since_id)
    print(f"[mb] library: {lib.get('active_count',0)} active pursuits | events: {len(events)}")

    # [02]
    print("[mb] [02] building prompt ...")
    prompt = build_prompt(lib, events)
    (OUT_DIR / f"mb_prompt_{char_id}_{user_id}.txt").write_text(prompt, encoding="utf-8")

    # [03]
    print("[mb] [03] LLM call ...")
    raw = call_llm(prompt)
    (OUT_DIR / f"mb_raw_{char_id}_{user_id}.txt").write_text(raw, encoding="utf-8")

    # [04]
    print("[mb] [04] parsing + validating ...")
    decision = parse_response(raw, lib, events)
    (OUT_DIR / f"mb_parsed_{char_id}_{user_id}.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dep_counts = {k: len(v) for k, v in (decision.get("deprecated_ignored") or {}).items() if v}
    print(
        f"[mb] decision: progress={len(decision['progress_updates'])} "
        f"done={len(decision['completed'])} "
        f"top5={len(decision['priority_order'])} "
        f"deprecated_ignored={dep_counts}"
    )

    # [05]
    print("[mb] [05] applying changes ...")
    # 尝试把全量 schedule_timeline 也喂进去（若 caller 用 --timeline-json，
    # events 只包含 since_id 之后的切片，auto_paused 需要更广的时间窗）
    full_timeline: list[dict] = []
    if timeline_json is not None:
        try:
            raw_obj = json.loads(Path(timeline_json).read_text(encoding="utf-8"))
            src = raw_obj.get("schedule_timeline") or raw_obj.get("timeline") or []
            if isinstance(src, list):
                full_timeline = src
        except Exception:
            full_timeline = []
    new_lib = apply_changes(lib, decision, events, schedule_timeline=full_timeline or None)
    auto_paused = new_lib.get("_last_mb_auto_paused", [])
    if auto_paused:
        print(f"[mb] auto_paused (code-driven): {len(auto_paused)} -> {[x['pursuit_id'] for x in auto_paused]}")

    # diff
    diff_text = emit_readable_diff(lib, new_lib, decision, events)
    (OUT_DIR / f"mb_diff_{char_id}_{user_id}.txt").write_text(diff_text, encoding="utf-8")
    print("")
    print(diff_text)
    print("")

    # [06]
    if dry_run:
        print("[mb] --dry-run: library NOT written back")
    else:
        # 保存前清掉临时 trace 字段
        new_lib.pop("_last_mb_auto_paused", None)
        p = pursuits_store.save(new_lib)
        print(f"[mb] saved -> {p}")

    print(f"[mb] readable diff -> {OUT_DIR / f'mb_diff_{char_id}_{user_id}.txt'}")

    # v3.2 注入模式：返回 MB-END payload 形状
    if return_payload:
        auto_paused = new_lib.pop("_last_mb_auto_paused", []) or []
        new_lib.pop("_last_ma_new_ids", None)  # 安全兜底
        accepted = (
            len(decision.get("progress_updates", []))
            + len(decision.get("completed", []))
            + len(auto_paused)
        )
        auto_paused_summary = (
            f"progress={len(decision.get('progress_updates', []))} "
            f"completed={len(decision.get('completed', []))} "
            f"auto_paused={len(auto_paused)}"
        )
        return {
            "new_library": build_new_library_payload(new_lib),
            "accepted_count": accepted,
            "auto_paused_summary": auto_paused_summary,
        }
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--char-id", default="mengya")
    ap.add_argument("--user-id", default="test_user")
    src = ap.add_mutually_exclusive_group()
    src.add_argument(
        "--events-dir",
        default=None,
        help="[legacy] 含 step_*.json 的目录（沙盒路径，字段不完整）",
    )
    src.add_argument(
        "--timeline-json",
        default=None,
        help="[recommended] 线上 schedule_timeline JSON（11 字段 schema）",
    )
    ap.add_argument(
        "--since-id",
        default=None,
        help="只处理时间严格在该 evt_id 之后的事件（仅 --timeline-json 有效）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff，不回写库")
    args = ap.parse_args(argv)

    events_dir: Path | None = None
    timeline_json: Path | None = None

    if args.timeline_json:
        timeline_json = Path(args.timeline_json)
        if not timeline_json.is_absolute():
            timeline_json = SANDBOX_ROOT / timeline_json
    elif args.events_dir:
        events_dir = Path(args.events_dir)
        if not events_dir.is_absolute():
            events_dir = SANDBOX_ROOT / events_dir
    else:
        # 默认 fallback（保持旧行为，便于回归）
        events_dir = SANDBOX_ROOT / "sandbox/out/runs/phase1_mengya_l123/seed_0"

    return run(
        args.char_id,
        args.user_id,
        events_dir=events_dir,
        timeline_json=timeline_json,
        since_id=args.since_id,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
