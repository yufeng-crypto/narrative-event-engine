# -*- coding: utf-8 -*-
"""character_pursuits 维护工作流 M-A：对话结束后的 pursuit 状态维护。

参见 sandbox_notes/character_pursuits_design_v0.md 节 5.1。

与 M-B 的核心差异：
  - 证据来源：对话 transcript（而非未来 24h schedule 事件）
  - event_refs -> message_refs（按 turn 编号）
  - 多一类变更：new_pursuits（对话中新冒出的目标）
  - 其余复用 M-B 的模块（parse / apply / rebuild_top5 / save / readable diff）

流水线（单次 LLM 调用）：
  [01] 数据加载（CODE）       -> load_library + load_chat
  [02] 构造 prompt（CODE）    -> build_prompt
  [03] LLM 维护判断（LLM）     -> call_llm
  [04] 解析 + 校验（CODE）    -> parse_response
  [05] 应用变更（CODE）       -> apply_changes + rebuild_top5
  [06] 保存 + 产出 readable  -> pursuits_store.save + emit_readable_diff

使用：
  python -m sandbox.tools.pursuits_maintain_after_chat \\
      --char-id mengya --user-id test_user \\
      --chat sandbox/fixtures/chats/mengya_test_user_20260420.json
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from sandbox.services import chat_adapter, pursuits_store
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

def load_chat(chat_path: Path) -> dict:
    """加载对话 fixture 并归一化 messages 字段。

    兼容三种 schema：
    1. 沙盒扁平 `messages: [{turn, role, ts, content}]`（本沙盒 fixture 历史格式）
    2. 线上 `sys.baji_records_50` 格式：`messages: [{assistant:{...}, user:{...}}]`
    3. 混合原始：顶层 `raw_baji_records_50` 字段（list 或 JSON 字符串）

    归一后 `messages` 保证是规范化 turn 列表（含 pseudo 标记）。
    额外补一个 `messages_filtered`（过滤掉 pseudo 后的版本）给 prompt 用。
    """
    obj = json.loads(chat_path.read_text(encoding="utf-8"))

    raw = None
    if "raw_baji_records_50" in obj:
        raw = obj["raw_baji_records_50"]
    elif "messages" in obj:
        raw = obj["messages"]
    else:
        raise ValueError(f"{chat_path} 缺少 messages / raw_baji_records_50 字段")

    normalized = chat_adapter.normalize_turns(raw)
    obj["messages"] = normalized
    obj["messages_filtered"] = chat_adapter.filter_real_messages(normalized)
    return obj


# ============================================================================
# [02] 构造 prompt
# ============================================================================

MAINTAIN_PROMPT = """你是一个 AI 伴侣角色的"自驱目标库维护者"。你的任务是：读角色和用户的**最近一段对话 transcript**，并根据对话内容对角色的 pursuits 库做状态维护。

与"日程生成后维护（M-B）"不同，这次你看的是**真实对话**——里面可能有已有 pursuit 的推进信号、也可能有**全新冒出来的目标**、也可能有用户明确劝阻某件事的情况。

---

## 输入 A：当前的 active pursuits 清单
{pursuits_block}

---

## 输入 B：对话 transcript（按 turn 编号）
{chat_block}

---

## 你要做的 8 件事（输出 JSON 时按此顺序）

⚠️ **证据硬要求（很重要，下述所有"状态性"桶都必须满足）**
- 凡是 progress_updates / completed / to_pause / to_revive / update_estimated_span / update_done_criterion 桶，**每条**都必须带：
  - `evidence_message_ref`: 对话里支撑该判断的**最具体一条** turn 号（整数）
  - `evidence_quote`: 从该 turn 的 content 中**原文节选**一段（≤ 40 字），**必须逐字**是该 turn 原文的子串
- 无法从对话里抄出原话支撑该变更的，**不要**做这个变更（漏判优于错判）
- `evidence_quote` 不是改写、不是概括——是**从原句里抠出**最短最有力的那段

### 1) progress_updates：对话里哪些内容推进了已有 pursuit？
- 逐 turn 扫描对话。如果某几条消息明显在推进某条 active pursuit，就记录：
  - `pursuit_id`
  - `message_refs`：对话里相关的 turn 编号数组
  - `new_current_stage`：用一句话（≤ 30 字）把 pursuit 当前阶段更新为"刚做了/定了什么、下一步要做什么"
  - `progress_log_entry`：一句话（≤ 40 字）摘要本次推进内容
  - `evidence_message_ref` + `evidence_quote`（硬要求，见上）
- 和日常闲聊（吃了什么、天气）不挂钩的内容**不要**强行归因。

### 2) completed：是否有 pursuit 达到了 done_criterion？
- 对照 `done_criterion` 字段严判。对话里只是"部分推进"的，**不要**算 completed。
- 输出 `{{"pursuit_id": "...", "reason": "...", "evidence_message_ref": N, "evidence_quote": "原句节选"}}`。

### 3) to_pause：对话中用户或角色明确劝阻/推迟了哪些 pursuit？
- 触发条件：用户明确说"别做这件事了"、"这事先放一放"，或角色自己说"我不想做了"。
- 必须有对话中的明确依据（在 reason 字段里引用具体 turn）+ `evidence_message_ref` + `evidence_quote`。
- 不能因为"这次对话没聊到"就 to_pause。

### 4) to_revive：对话里有没有把之前 paused 的 pursuit 重新拾起来？
- 只在看到对话里明显在推进一个当前 `paused` 的 pursuit 时填。
- 这次输入里如果没有 paused 项，直接返回空数组。
- 带 `evidence_message_ref` + `evidence_quote`。

### 5) new_pursuits：对话里有没有**全新冒出的目标**值得纳入库？
- 条件：这是一件**明确的、有推进动作的事**（不是情绪表达、不是一时想法）。
- 每条必须包含：
  - `title`（≤ 20 字）
  - `dimension`（必须是 9 维之一：家人 / 社交 / 工作 / 兴趣 / 约定 / 感情 / 误会 / 健康 / 生活）
  - `current_stage`（≤ 30 字，"刚约定/发现了什么，下一步做什么"）
  - `done_criterion`（≤ 30 字，明确的完成标志）
  - `urgency`（hard / medium / soft）
  - `estimated_span`（如 "1周" / "3天" / "1月" / "持续性"）
  - `origin_hint`（本次对话里的依据，引用 turn 编号）
  - `evidence_message_ref`（触发本次 new 的那条 turn 号）
- **宁可漏判，不要滥判**。如果对话里只是随口一说、没有实际推进动作，**不要**建新 pursuit。
- new_pursuits 不需要 evidence_quote（是创造性动作，不是修改）。

- ⚠️ **单轮闭环反例（严格排除）**：
  - 如果一件事**在本次对话内部**就完成了"提出→执行→完成"的整条链路，**不要**建 new_pursuit。
  - 典型样例：
    - ❌ 用户让角色"今晚给我带饭"→ 角色回"已送到你门口"→ 用户回"收到谢谢"：这是一次**事件级完成**，不是需要未来多步推进的目标。
    - ❌ 用户说"帮我查下快递"→ 角色查到告诉用户 → 用户说"知道了"：当场闭环，不入库。
    - ❌ 用户让角色"念首诗"→ 角色念了 → 用户"好听"：当场闭环，不入库。
  - 判定标准：**到 transcript 结束时，如果这件事已经达到 done_criterion，就不应该建它。** 只有还需要未来动作推进的，才是 pursuit。
  - ✅ 反例之反例（这些要建）：
    - 用户"下周陪我去拜访蔡徐坤" → 角色答应（对话里还没去）：建 new_pursuit，done=拜访完成。
    - 用户"周末一起布置新家" → 角色答应（对话里还没做）：建 new_pursuit。

### 6) update_estimated_span：调整已有 pursuit 的时长预期
- **仅在以下情境触发**：
  - (a) 用户或角色**明确在对话中说了新的时间预期**（"下周前必须搞定" / "这事拖到下个月再看吧"）
  - (b) 剧情出现**重大延迟/加速信号**（"项目被砍了" / "截止日期提前到周五"）
- 每条必须包含：
  - `pursuit_id`
  - `new_span`（必须是枚举之一："X天" / "X周" / "X月" / "持续性"）
  - `reason`（≤ 30 字）
  - `evidence_message_ref` + `evidence_quote`（硬要求）
- **不要**因为"你觉得原本估得短/长"就调整——那是主观判断。只有对话里有**原话**才能改。

### 7) update_done_criterion：修订已有 pursuit 的完成条件
- **仅在以下情境触发**：
  - (a) 对话里用户/角色**明确重新定义了完成标准**（"等主厨点头才算过关" / "只要见到人就算完成"）
  - (b) 发现原条件明显描述错误或含混，**对话里有修订性表达**
- 每条必须包含：
  - `pursuit_id`
  - `new_criterion`（≤ 100 字）
  - `reason`（≤ 30 字）
  - `evidence_message_ref` + `evidence_quote`（硬要求）
- **不要**偷偷放宽条件以便"提前完成"。

### 8) priority_order：下次 P2 应该优先推进的 top-5 pursuit_id
- 只从本次处理**之后**的 active 列表里挑（包含新建的 new_pursuits 的 id 会在 CODE 层分配，你在这里**无需**把 new_pursuit 放进 priority_order——CODE 层会自动把 new 加进候选）
- 优先规则：紧迫（hard > medium > soft）→ 短期 span → 剧情连续性
- 最多 5 条 id（必须来自输入 A 中 active 状态的 pursuit）
- priority_order 不需要 evidence。

---

## 输出格式（严格 JSON，不要外层 markdown 围栏）

```
{{
  "progress_updates": [
    {{"pursuit_id": "pur_...", "message_refs": [1, 3, 5], "new_current_stage": "...", "progress_log_entry": "...",
      "evidence_message_ref": 3, "evidence_quote": "原句中的一段≤40字"}}
  ],
  "completed": [
    {{"pursuit_id": "pur_...", "reason": "...",
      "evidence_message_ref": 7, "evidence_quote": "原句节选"}}
  ],
  "to_pause": [
    {{"pursuit_id": "pur_...", "reason": "turn13 用户说...",
      "evidence_message_ref": 13, "evidence_quote": "别做这个了"}}
  ],
  "to_revive": [
    {{"pursuit_id": "pur_...", "reason": "...",
      "evidence_message_ref": 9, "evidence_quote": "..."}}
  ],
  "new_pursuits": [
    {{"title": "...", "dimension": "约定", "current_stage": "...",
      "done_criterion": "...", "urgency": "medium", "estimated_span": "1周",
      "origin_hint": "turn9-12 用户提议...", "evidence_message_ref": 10}}
  ],
  "update_estimated_span": [
    {{"pursuit_id": "pur_...", "new_span": "3天", "reason": "截止日期提前",
      "evidence_message_ref": 14, "evidence_quote": "周五之前搞定"}}
  ],
  "update_done_criterion": [
    {{"pursuit_id": "pur_...", "new_criterion": "...", "reason": "...",
      "evidence_message_ref": 11, "evidence_quote": "..."}}
  ],
  "priority_order": ["pur_aaa", "pur_bbb", "pur_ccc", "pur_ddd", "pur_eee"]
}}
```

### 硬约束
- progress_updates / completed / to_pause / to_revive / update_estimated_span / update_done_criterion / priority_order 里的 `pursuit_id` 必须来自输入 A。不能编造。
- `message_refs` / `evidence_message_ref` 里的 turn 编号必须来自输入 B。
- `evidence_quote` 必须是该 turn 原文的子串（允许空白 / 换行归一化）。
- 同一个 pursuit_id 不能同时出现在多个互斥桶里（progress / completed / pause / revive 互斥；update_estimated_span 不能与 completed 同现）。
- 只输出 JSON，不要任何解释或 markdown。
"""


def _fmt_pursuits_block(pursuits: list[dict]) -> str:
    """展示 active 和 paused（paused 用于判断 to_revive）"""
    lines = []
    actives = [p for p in pursuits if p.get("status") == "active"]
    paused = [p for p in pursuits if p.get("status") == "paused"]

    lines.append(f"[active: {len(actives)} 条]")
    for i, p in enumerate(actives, 1):
        lines.append(
            f"#{i}  id={p['id']}  [{p.get('dimension','?')}/{p.get('urgency','?')}/{p.get('estimated_span','?')}]"
        )
        lines.append(f"     title: {p.get('title','')}")
        lines.append(f"     stage: {p.get('current_stage','')}")
        lines.append(f"     done:  {p.get('done_criterion','')}")

    if paused:
        lines.append("")
        lines.append(f"[paused: {len(paused)} 条（用于判断 to_revive）]")
        for p in paused:
            lines.append(f"  id={p['id']}  title={p.get('title','')}  stage={p.get('current_stage','')}")

    return "\n".join(lines)


def _fmt_chat_block(chat: dict) -> str:
    """格式化对话 transcript 给 LLM 看。

    伪消息（`pseudo=True`）做特殊渲染：不把整段 JSON 喂给 LLM，而是翻译成
    一句中文摘要（见 chat_adapter.describe_pseudo）。prompt 里标记 `[pseudo]`。
    这样 LLM 不会把 schedule_update 这类系统注入当成用户在说话。
    """
    lines = []
    lines.append(f"session started_at: {chat.get('started_at','?')}  ended_at: {chat.get('ended_at','?')}")
    if chat.get("notes"):
        lines.append(f"notes: {chat['notes']}")
    lines.append("")
    for m in chat.get("messages", []):
        role = m.get("role", "?")
        turn = m.get("turn", "?")
        content = m.get("content", "")
        is_pseudo = m.get("pseudo", False)
        if is_pseudo:
            content = chat_adapter.describe_pseudo(content)
            lines.append(f"turn{turn:02d} [{role}] [pseudo] {content}")
        else:
            lines.append(f"turn{turn:02d} [{role}]  {content}")
    return "\n".join(lines)


def build_prompt(lib: dict, chat: dict) -> str:
    return MAINTAIN_PROMPT.format(
        pursuits_block=_fmt_pursuits_block(lib.get("pursuits", [])),
        chat_block=_fmt_chat_block(chat),
    )


# ============================================================================
# [03] LLM 调用
# ============================================================================

def call_llm(prompt: str) -> str:
    cfg = TOOL_KEY_MAP["doubao-1.5 pro 32k"]
    print(f"[ma] prompt chars = {len(prompt)}, calling LLM ...")
    t0 = time.time()
    raw = call_doubao_raw(
        model=cfg["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=float(cfg["temperature"]),
        max_tokens=4000,
    )
    dt = time.time() - t0
    print(f"[ma] LLM done in {dt:.1f}s, {len(raw)} chars")
    return raw


# ============================================================================
# [04] 解析 + 校验
# ============================================================================

class MaintainParseError(ValueError):
    pass


_VALID_DIMS = {"家人", "社交", "工作", "兴趣", "约定", "感情", "误会", "健康", "生活", "其他"}
_VALID_URGENCIES = {"hard", "medium", "soft"}

# estimated_span 合法值 pattern（v3 update_estimated_span 用）
# 接受: "X天" / "X周" / "X月" / "持续性"（X 可多位数字）
_SPAN_RE = re.compile(r"^(?:\d+\s*(?:天|周|月)|持续性)$")


def _normalize_ws(s: str) -> str:
    """把 \\n \\t 多空格压成单空格，供 evidence_quote substring 比对容错。"""
    import re as _re
    return _re.sub(r"\s+", " ", (s or "").strip())


def _evidence_ok(turn_idx, quote, turns_by_id: dict) -> tuple[bool, str]:
    """v3 evidence_quote 硬校验。返回 (ok, reason)；ok=False 时 reason 可读。"""
    if not isinstance(turn_idx, int):
        return False, f"evidence_message_ref={turn_idx!r} 不是整数"
    if turn_idx not in turns_by_id:
        return False, f"evidence_message_ref={turn_idx} 不在对话 turn 范围"
    if not isinstance(quote, str) or not quote.strip():
        return False, "evidence_quote 为空"
    if len(quote) > 100:
        return False, f"evidence_quote 超长 ({len(quote)} > 100)"
    turn_content = turns_by_id[turn_idx].get("content", "") or ""
    if _normalize_ws(quote) not in _normalize_ws(turn_content):
        return False, (
            f"evidence_quote 不是 turn{turn_idx} 的原文子串: "
            f"quote={quote[:30]!r} not in content={turn_content[:60]!r}"
        )
    return True, ""


def parse_response(raw: str, lib: dict, chat: dict) -> dict:
    """v3 parser：
    - 8 桶（新增 update_estimated_span / update_done_criterion）
    - 状态性桶的每一条都做 evidence_quote 硬校验；失败进 obj['rejected']（单项驳回，不整体失败）
    - 其它结构性失败（JSON 坏 / pursuit_id 不在库 / message_refs 超范围 / 互斥冲突）仍 raise
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

    for k in (
        "progress_updates", "completed", "to_pause", "to_revive",
        "new_pursuits", "update_estimated_span", "update_done_criterion",
        "priority_order",
    ):
        obj.setdefault(k, [])
    obj.setdefault("rejected", [])  # v3：evidence 等单项驳回会落这里

    # LLM 容错：message_refs / evidence_message_ref 可能混 "turn14" / "14" / 14
    def _coerce_turn(v):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            m = re.search(r"(\d+)", v)
            if m:
                return int(m.group(1))
        return v

    for it in obj["progress_updates"]:
        if isinstance(it, dict):
            if "message_refs" in it:
                it["message_refs"] = [_coerce_turn(x) for x in (it["message_refs"] or [])]
            if "evidence_message_ref" in it:
                it["evidence_message_ref"] = _coerce_turn(it["evidence_message_ref"])
    for bucket_name in (
        "completed", "to_pause", "to_revive",
        "new_pursuits", "update_estimated_span", "update_done_criterion",
    ):
        for it in obj[bucket_name]:
            if isinstance(it, dict) and "evidence_message_ref" in it:
                it["evidence_message_ref"] = _coerce_turn(it["evidence_message_ref"])

    valid_ids = {p["id"] for p in lib.get("pursuits", [])}
    active_ids = {p["id"] for p in lib.get("pursuits", []) if p.get("status") == "active"}
    paused_ids = {p["id"] for p in lib.get("pursuits", []) if p.get("status") == "paused"}
    valid_turns = {m["turn"] for m in chat.get("messages", []) if "turn" in m}
    turns_by_id = {m["turn"]: m for m in chat.get("messages", []) if "turn" in m}

    errors: list[str] = []  # 结构性错误（致命），直接 raise

    def _drop_with_reason(bucket_name: str, index: int, reason: str) -> None:
        """单项驳回：把 bucket[index] 搬到 obj['rejected']，带 reason。"""
        item = obj[bucket_name][index]
        rej = {"bucket": bucket_name, "item": item, "reason": reason}
        obj["rejected"].append(rej)

    def _filter_bucket(bucket_name: str, predicate):
        """按 predicate 过滤桶；predicate 返回 (ok, reason)。失败项搬去 rejected。"""
        kept = []
        for i, it in enumerate(obj[bucket_name]):
            ok, reason = predicate(it)
            if ok:
                kept.append(it)
            else:
                _drop_with_reason(bucket_name, i, reason)
        obj[bucket_name] = kept

    # ---------- pursuit_id 有效性 + status 检查（驳回，不 raise）----------
    def _id_ok(it, must_be_active: bool = False, must_be_paused: bool = False):
        pid = it.get("pursuit_id") if isinstance(it, dict) else None
        if pid not in valid_ids:
            return False, f"pursuit_id={pid!r} 不在库中"
        if must_be_active and pid not in active_ids:
            return False, f"pursuit_id={pid!r} 不是 active 状态"
        if must_be_paused and pid not in paused_ids:
            return False, f"pursuit_id={pid!r} 不是 paused 状态"
        return True, ""

    _filter_bucket("progress_updates", lambda it: _id_ok(it, must_be_active=True))
    _filter_bucket("completed",       lambda it: _id_ok(it, must_be_active=True))
    _filter_bucket("to_pause",        lambda it: _id_ok(it, must_be_active=True))
    _filter_bucket("to_revive",       lambda it: _id_ok(it, must_be_paused=True))
    _filter_bucket("update_estimated_span", lambda it: _id_ok(it, must_be_active=True))
    _filter_bucket("update_done_criterion", lambda it: _id_ok(it, must_be_active=True))

    # ---------- message_refs 超范围（单项驳回）----------
    def _refs_ok(it):
        refs = it.get("message_refs") or []
        for r in refs:
            if r not in valid_turns:
                return False, f"message_refs 含未知 turn {r}"
        return True, ""
    _filter_bucket("progress_updates", _refs_ok)

    # ---------- evidence_quote 硬校验（v3 核心新增，单项驳回）----------
    def _evidence_guard(it):
        ref = it.get("evidence_message_ref")
        quote = it.get("evidence_quote")
        ok, reason = _evidence_ok(ref, quote, turns_by_id)
        if not ok:
            return False, f"evidence 校验失败: {reason}"
        return True, ""

    for bucket in ("progress_updates", "completed", "to_pause", "to_revive",
                   "update_estimated_span", "update_done_criterion"):
        _filter_bucket(bucket, _evidence_guard)

    # new_pursuits: 只要 evidence_message_ref 有效（不要求 quote）
    def _np_ref_ok(it):
        ref = it.get("evidence_message_ref")
        if not isinstance(ref, int) or ref not in valid_turns:
            return False, f"evidence_message_ref={ref!r} 无效"
        return True, ""
    _filter_bucket("new_pursuits", _np_ref_ok)

    # ---------- priority_order：非法 id 直接砍掉（不驳回整个桶）----------
    po_kept = []
    for pid in obj["priority_order"]:
        if pid in valid_ids:
            po_kept.append(pid)
        else:
            obj["rejected"].append({
                "bucket": "priority_order",
                "item": pid,
                "reason": "pursuit_id 不在库中",
            })
    obj["priority_order"] = po_kept

    # ---------- new_pursuits 字段完整性（结构性要求，单项驳回）----------
    def _np_fields_ok(it):
        required = ["title", "dimension", "current_stage",
                    "done_criterion", "urgency", "estimated_span", "origin_hint"]
        for f in required:
            if not it.get(f):
                return False, f"缺字段 {f}"
        if it.get("dimension") not in _VALID_DIMS:
            return False, f"dimension={it.get('dimension')!r} 不在 9 维之内"
        if it.get("urgency") not in _VALID_URGENCIES:
            return False, f"urgency={it.get('urgency')!r} 非法"
        return True, ""
    _filter_bucket("new_pursuits", _np_fields_ok)

    # ---------- update_estimated_span: new_span 枚举校验 ----------
    def _span_ok(it):
        new_span = (it.get("new_span") or "").strip()
        if not new_span:
            return False, "缺 new_span"
        if not _SPAN_RE.match(new_span):
            return False, f"new_span={new_span!r} 不符合枚举（X天/X周/X月/持续性）"
        return True, ""
    _filter_bucket("update_estimated_span", _span_ok)

    # ---------- update_done_criterion: new_criterion 长度 ----------
    def _criterion_ok(it):
        nc = (it.get("new_criterion") or "").strip()
        if not nc:
            return False, "缺 new_criterion"
        if len(nc) > 100:
            return False, f"new_criterion 超长 ({len(nc)} > 100)"
        return True, ""
    _filter_bucket("update_done_criterion", _criterion_ok)

    # ---------- 互斥校验（同 pid 不能同时出现在两个互斥桶里）----------
    def _ids_in(bucket_name):
        return {it.get("pursuit_id") for it in obj[bucket_name] if isinstance(it, dict)}

    # (a) progress / completed / pause / revive 四者两两互斥
    state_buckets = ("progress_updates", "completed", "to_pause", "to_revive")
    for a in range(len(state_buckets)):
        for b in range(a + 1, len(state_buckets)):
            overlap = _ids_in(state_buckets[a]) & _ids_in(state_buckets[b])
            if overlap:
                errors.append(f"{state_buckets[a]} 和 {state_buckets[b]} 互斥冲突: {overlap}")
    # (b) update_estimated_span / completed 互斥
    overlap = _ids_in("update_estimated_span") & _ids_in("completed")
    if overlap:
        errors.append(f"update_estimated_span 和 completed 互斥冲突: {overlap}")

    if errors:
        raise MaintainParseError(
            "LLM 输出结构性校验失败（无法容错）:\n  - " + "\n  - ".join(errors)
        )

    return obj


# ============================================================================
# [05] 应用变更
# ============================================================================

def _next_seq_for_today(lib: dict, today: str) -> int:
    """在库中已有的 pur_<today>_NNN 里取最大 seq+1，防止 id 冲突。"""
    prefix = f"pur_{today}_"
    max_seq = 0
    for p in lib.get("pursuits", []):
        pid = p.get("id", "")
        if pid.startswith(prefix):
            try:
                seq = int(pid[len(prefix):])
                max_seq = max(max_seq, seq)
            except ValueError:
                pass
    return max_seq + 1


def apply_changes(lib: dict, decision: dict, chat: dict) -> dict:
    """返回新的 lib 对象（不改 in-place）。

    v3 关键变更：
    - 删除 next_likely_actions 字段（new_pursuits 不再写入）
    - 新增 update_estimated_span / update_done_criterion 两桶应用
    - progress_log.ts 使用**对话 turn 的时间戳**（角色时间）而非 apply 时的 now_iso
    """
    new_lib = copy.deepcopy(lib)
    now = datetime.now().astimezone()
    now_iso = now.isoformat(timespec="seconds")
    today_str = now.strftime("%Y%m%d")

    by_id = {p["id"]: p for p in new_lib["pursuits"]}
    turns_by_id = {m["turn"]: m for m in chat.get("messages", []) if "turn" in m}

    def _ts_for_ref(ref) -> str:
        """v3: progress_log.ts 优先取 evidence turn 的 ts（角色时间）；fallback 到 now_iso。"""
        if isinstance(ref, int) and ref in turns_by_id:
            ts = turns_by_id[ref].get("ts") or ""
            if ts:
                return ts
        return now_iso

    # 1) progress_updates
    for it in decision["progress_updates"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        refs = it.get("message_refs") or []
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        new_stage = (it.get("new_current_stage") or "").strip()
        if new_stage:
            p["current_stage"] = new_stage
        p.setdefault("progress_log", []).append({
            "ts": log_ts,
            "source": "chat",
            "by": "MA",
            "session_id": chat.get("session_id"),
            "summary": (it.get("progress_log_entry") or "").strip(),
            "message_refs": refs,
            "evidence_ref": f"turn:{ref}" if ref is not None else None,
            "evidence_quote": it.get("evidence_quote"),
        })
        p["updated_at"] = now_iso

    # 2) completed
    for it in decision["completed"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        p["status"] = "done"
        p["done_at"] = now_iso
        p["updated_at"] = now_iso
        p.setdefault("progress_log", []).append({
            "ts": log_ts,
            "source": "chat",
            "by": "MA",
            "session_id": chat.get("session_id"),
            "summary": "[DONE] " + (it.get("reason") or "").strip(),
            "message_refs": [],
            "evidence_ref": f"turn:{ref}" if ref is not None else None,
            "evidence_quote": it.get("evidence_quote"),
        })

    # 3) to_pause
    for it in decision["to_pause"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        p["status"] = "paused"
        p["updated_at"] = now_iso
        p.setdefault("progress_log", []).append({
            "ts": log_ts,
            "source": "chat",
            "by": "MA",
            "session_id": chat.get("session_id"),
            "summary": "[PAUSE] " + (it.get("reason") or "").strip(),
            "message_refs": [],
            "evidence_ref": f"turn:{ref}" if ref is not None else None,
            "evidence_quote": it.get("evidence_quote"),
        })

    # 4) to_revive
    for it in decision["to_revive"]:
        pid = it["pursuit_id"]
        p = by_id[pid]
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        if p.get("status") == "paused":
            p["status"] = "active"
            p["updated_at"] = now_iso
            p.setdefault("progress_log", []).append({
                "ts": log_ts,
                "source": "chat",
                "by": "MA",
                "session_id": chat.get("session_id"),
                "summary": "[REVIVE] " + (it.get("reason") or "").strip(),
                "message_refs": [],
                "evidence_ref": f"turn:{ref}" if ref is not None else None,
                "evidence_quote": it.get("evidence_quote"),
            })

    # 5) new_pursuits —— 新分支（M-B 没有）
    #    v3: 不再写 next_likely_actions 字段
    new_ids: list[str] = []
    seq = _next_seq_for_today(new_lib, today_str)
    for np in decision["new_pursuits"]:
        pid = f"pur_{today_str}_{seq:03d}"
        seq += 1
        ref = np.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        new_p = {
            "id": pid,
            "title": np["title"].strip(),
            "dimension": np["dimension"].strip(),
            "current_stage": np["current_stage"].strip(),
            "done_criterion": np["done_criterion"].strip(),
            "urgency": np["urgency"].strip(),
            "estimated_span": np["estimated_span"].strip(),
            "origin_hint": np["origin_hint"].strip(),
            "status": "active",
            "created_at": now_iso,
            "updated_at": now_iso,
            "done_at": None,
            "progress_log": [{
                "ts": log_ts,
                "source": "chat",
                "by": "MA",
                "session_id": chat.get("session_id"),
                "summary": "[NEW] 本次对话新建，origin: " + np["origin_hint"].strip(),
                "message_refs": [],
                "evidence_ref": f"turn:{ref}" if ref is not None else None,
            }],
            "linked_schedule_events": [],
        }
        new_lib["pursuits"].append(new_p)
        by_id[pid] = new_p
        new_ids.append(pid)

    # 5b) update_estimated_span（v3 新增，MA 独占）
    for it in decision.get("update_estimated_span", []):
        pid = it["pursuit_id"]
        p = by_id[pid]
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        old_span = p.get("estimated_span", "")
        new_span = it["new_span"].strip()
        p["estimated_span"] = new_span
        p["updated_at"] = now_iso
        p.setdefault("progress_log", []).append({
            "ts": log_ts,
            "source": "chat",
            "by": "MA",
            "session_id": chat.get("session_id"),
            "summary": f"[span 调整] {old_span} -> {new_span}; " + (it.get("reason") or "").strip(),
            "message_refs": [],
            "evidence_ref": f"turn:{ref}" if ref is not None else None,
            "evidence_quote": it.get("evidence_quote"),
        })

    # 5c) update_done_criterion（v3 新增，MA 独占）
    for it in decision.get("update_done_criterion", []):
        pid = it["pursuit_id"]
        p = by_id[pid]
        ref = it.get("evidence_message_ref")
        log_ts = _ts_for_ref(ref)
        old_crit = p.get("done_criterion", "")
        new_crit = it["new_criterion"].strip()
        p["done_criterion"] = new_crit
        p["updated_at"] = now_iso
        p.setdefault("progress_log", []).append({
            "ts": log_ts,
            "source": "chat",
            "by": "MA",
            "session_id": chat.get("session_id"),
            "summary": f"[criterion 修订] {old_crit!r} -> {new_crit!r}; " + (it.get("reason") or "").strip(),
            "message_refs": [],
            "evidence_ref": f"turn:{ref}" if ref is not None else None,
            "evidence_quote": it.get("evidence_quote"),
        })

    # 6) 重算计数
    active_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "active")
    done_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "done")
    dropped_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "dropped")
    paused_count = sum(1 for p in new_lib["pursuits"] if p["status"] == "paused")
    new_lib["active_count"] = active_count
    new_lib["done_count"] = done_count
    new_lib["dropped_count"] = dropped_count
    new_lib["paused_count"] = paused_count

    # 7) top-5 重建（M-A 专用策略：**对话里刚聊到的 pursuit 优先级最高**）
    #    ------------------------------------------------------------
    #    用户诉求："用户最新对话的内容优先级最高，不要延迟到下次 M-B 才生效"
    #    策略（按层叠加，不重不漏）：
    #      第 1 层：new_pursuits        -- 用户刚产生的全新需求
    #      第 2 层：progress_updates    -- 用户刚聊到的既有目标
    #      第 3 层：to_revive           -- 被拾起的 paused 目标
    #      第 4 层：LLM priority_order  -- LLM 认为"还应该记得推进"的（排除已 pause/done）
    #      第 5 层：rebuild_top5_from_order 内部启发式补尾
    paused_or_done = (
        {it["pursuit_id"] for it in decision["to_pause"]}
        | {it["pursuit_id"] for it in decision["completed"]}
    )
    touched: list[str] = []
    seen: set[str] = set()

    def _push(pid: str):
        if pid and pid not in seen and pid not in paused_or_done:
            touched.append(pid)
            seen.add(pid)

    # 第 1 层：new
    for pid in new_ids:
        _push(pid)
    # 第 2 层：progress（LLM 输出顺序即最近聊到的顺序）
    for it in decision["progress_updates"]:
        _push(it["pursuit_id"])
    # 第 3 层：revive
    for it in decision["to_revive"]:
        _push(it["pursuit_id"])
    # 第 4 层：LLM priority_order 里余下的
    for pid in decision.get("priority_order", []) or []:
        _push(pid)

    pursuits_store.rebuild_top5_from_order(new_lib, touched)

    new_lib["last_maintenance_at"] = now_iso
    # 附加 trace：本轮新建的 id（方便 diff 展示）
    new_lib["_last_ma_new_ids"] = new_ids

    return new_lib


# ============================================================================
# [06] 人肉 review
# ============================================================================

def emit_readable_diff(old_lib: dict, new_lib: dict, decision: dict, chat: dict) -> str:
    old_by_id = {p["id"]: p for p in old_lib["pursuits"]}
    new_by_id = {p["id"]: p for p in new_lib["pursuits"]}
    new_ids = new_lib.get("_last_ma_new_ids", [])

    lines: list[str] = []
    lines.append("========== M-A 维护结果 diff ==========")
    lines.append(f"char: {new_lib['char_id']} | user: {new_lib['user_id']}")
    lines.append(f"session: {chat.get('session_id','?')} | messages: {len(chat.get('messages', []))}")
    lines.append(
        f"active: {old_lib.get('active_count',0)} -> {new_lib.get('active_count',0)}  | "
        f"done: {old_lib.get('done_count',0)} -> {new_lib.get('done_count',0)}  | "
        f"paused: {old_lib.get('paused_count',0)} -> {new_lib.get('paused_count',0)}  | "
        f"dropped: {old_lib.get('dropped_count',0)} -> {new_lib.get('dropped_count',0)}"
    )
    lines.append("")

    lines.append(f"--- [1] progress_updates: {len(decision['progress_updates'])} ---")
    for it in decision["progress_updates"]:
        pid = it["pursuit_id"]
        old_p = old_by_id.get(pid, {})
        new_p = new_by_id.get(pid, {})
        lines.append(f"  {pid}  {new_p.get('title','')}")
        lines.append(f"    message_refs: turn{it.get('message_refs', [])}")
        if old_p.get("current_stage") != new_p.get("current_stage"):
            lines.append(f"    stage:  \"{old_p.get('current_stage','')}\"")
            lines.append(f"      -> \"{new_p.get('current_stage','')}\"")
        lines.append(f"    + log: {it.get('progress_log_entry','')}")

    lines.append("")
    lines.append(f"--- [2] completed: {len(decision['completed'])} ---")
    for it in decision["completed"]:
        pid = it["pursuit_id"]
        lines.append(f"  {pid}  {new_by_id.get(pid,{}).get('title','')}")
        lines.append(f"    reason: {it.get('reason','')}")

    lines.append("")
    lines.append(f"--- [3] to_pause: {len(decision['to_pause'])} ---")
    for it in decision["to_pause"]:
        pid = it["pursuit_id"]
        lines.append(f"  {pid}  {new_by_id.get(pid,{}).get('title','')}")
        lines.append(f"    reason: {it.get('reason','')}")

    lines.append("")
    lines.append(f"--- [4] to_revive: {len(decision['to_revive'])} ---")
    for it in decision["to_revive"]:
        pid = it["pursuit_id"]
        lines.append(f"  {pid}  {new_by_id.get(pid,{}).get('title','')}")
        lines.append(f"    reason: {it.get('reason','')}")

    lines.append("")
    lines.append(f"--- [5] new_pursuits: {len(decision['new_pursuits'])} ---")
    for pid, np_raw in zip(new_ids, decision["new_pursuits"]):
        p = new_by_id.get(pid, {})
        lines.append(
            f"  {pid}  [{p.get('dimension','?')}/{p.get('urgency','?')}/{p.get('estimated_span','?')}]  {p.get('title','')}"
        )
        lines.append(f"    stage: {p.get('current_stage','')}")
        lines.append(f"    done:  {p.get('done_criterion','')}")
        lines.append(f"    origin:{p.get('origin_hint','')}")

    # v3 新增：update_estimated_span / update_done_criterion
    upd_span = decision.get("update_estimated_span", [])
    lines.append("")
    lines.append(f"--- [5b] update_estimated_span: {len(upd_span)} ---")
    for it in upd_span:
        pid = it["pursuit_id"]
        old_p = old_by_id.get(pid, {})
        new_p = new_by_id.get(pid, {})
        lines.append(f"  {pid}  {new_p.get('title','')}")
        lines.append(
            f"    span: {old_p.get('estimated_span','?')} -> {new_p.get('estimated_span','?')}"
        )
        lines.append(f"    reason: {it.get('reason','')}")
        lines.append(
            f"    evidence: turn{it.get('evidence_message_ref')} \"{it.get('evidence_quote','')}\""
        )

    upd_crit = decision.get("update_done_criterion", [])
    lines.append("")
    lines.append(f"--- [5c] update_done_criterion: {len(upd_crit)} ---")
    for it in upd_crit:
        pid = it["pursuit_id"]
        old_p = old_by_id.get(pid, {})
        new_p = new_by_id.get(pid, {})
        lines.append(f"  {pid}  {new_p.get('title','')}")
        lines.append(f"    old: {old_p.get('done_criterion','')!r}")
        lines.append(f"    new: {new_p.get('done_criterion','')!r}")
        lines.append(f"    reason: {it.get('reason','')}")
        lines.append(
            f"    evidence: turn{it.get('evidence_message_ref')} \"{it.get('evidence_quote','')}\""
        )

    # v3 新增：单项驳回的 rejected 列表（evidence 失败 / 字段缺失 / id 不存在等）
    rejected = decision.get("rejected", []) or []
    lines.append("")
    lines.append(f"--- [5d] rejected (单项驳回): {len(rejected)} ---")
    for rej in rejected:
        bucket = rej.get("bucket", "?")
        reason = rej.get("reason", "?")
        item = rej.get("item")
        # item 可能是 dict 或 str（priority_order 里的裸 id）
        if isinstance(item, dict):
            tag = item.get("pursuit_id") or item.get("title") or "<?>"
        else:
            tag = str(item)
        lines.append(f"  [{bucket}] {tag}  <- {reason}")

    lines.append("")
    lines.append(f"--- [6] new pursuits_top5_cache ---")
    for i, p in enumerate(new_lib.get("pursuits_top5_cache", []), 1):
        marker = " [NEW]" if p.get("id") in new_ids else ""
        lines.append(
            f"  {i}. {p.get('id')}  [{p.get('urgency','?')}/{p.get('estimated_span','?')}]  {p.get('title','')}{marker}"
        )

    return "\n".join(lines)


# ============================================================================
# Pipeline
# ============================================================================

def run(
    char_id: str,
    user_id: str,
    chat_path: Path,
    dry_run: bool = False,
    *,
    pursuits_library_raw: str | None = None,
    return_payload: bool = False,
):
    """M-A 主流程。

    两种调用模式（同 Cold Start）：

    1. **Fixture 模式**：`pursuits_library_raw=None` → 读/写本地 fixture；返回 int。
    2. **v3.2 注入模式**：传 `pursuits_library_raw`（字符串 / "" / "null"）→
       绕过本地读；若 `return_payload=True`，返回 MA-END 形状的 dict
       `{new_library, accepted_count, diff_summary}`。

    注：MA 的注入前提是库已存在（空库情况 CS 还没跑完）；若收到空库注入，
    视作 LLM 无事可做，返回一个 no-op payload（new_library.pursuits=[]）。
    """
    print(f"[ma] [01] loading library ({char_id}, {user_id}) and chat from {chat_path} ...")
    if pursuits_library_raw is not None:
        lib = parse_injected_library(pursuits_library_raw, char_id, user_id)
        if not lib.get("pursuits"):
            print(f"[ma] WARN: injection is empty for ({char_id}, {user_id}); MA no-op")
            if return_payload:
                return {
                    "new_library": build_new_library_payload(lib),
                    "accepted_count": 0,
                    "diff_summary": "progress=0 completed=0 paused=0 revived=0 new=0",
                }
            return 2
    else:
        lib = pursuits_store.load(char_id, user_id)
        if lib is None:
            print(f"[ma] ERROR: library not found for ({char_id}, {user_id}); run pursuits_cold_start first")
            return 2
    chat = load_chat(chat_path)
    print(f"[ma] library: {lib.get('active_count',0)} active | chat: {len(chat.get('messages', []))} messages")

    print("[ma] [02] building prompt ...")
    prompt = build_prompt(lib, chat)
    (OUT_DIR / f"ma_prompt_{char_id}_{user_id}.txt").write_text(prompt, encoding="utf-8")

    print("[ma] [03] LLM call ...")
    raw = call_llm(prompt)
    (OUT_DIR / f"ma_raw_{char_id}_{user_id}.txt").write_text(raw, encoding="utf-8")

    print("[ma] [04] parsing + validating ...")
    decision = parse_response(raw, lib, chat)
    (OUT_DIR / f"ma_parsed_{char_id}_{user_id}.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[ma] decision: progress={len(decision['progress_updates'])} "
        f"done={len(decision['completed'])} "
        f"pause={len(decision['to_pause'])} "
        f"revive={len(decision['to_revive'])} "
        f"new={len(decision['new_pursuits'])} "
        f"upd_span={len(decision.get('update_estimated_span', []))} "
        f"upd_crit={len(decision.get('update_done_criterion', []))} "
        f"rejected={len(decision.get('rejected', []))} "
        f"top5={len(decision['priority_order'])}"
    )

    print("[ma] [05] applying changes ...")
    new_lib = apply_changes(lib, decision, chat)

    diff_text = emit_readable_diff(lib, new_lib, decision, chat)
    (OUT_DIR / f"ma_diff_{char_id}_{user_id}.txt").write_text(diff_text, encoding="utf-8")
    print("")
    print(diff_text)
    print("")

    if dry_run:
        print("[ma] --dry-run: library NOT written back")
    else:
        # save 前清掉临时字段
        new_lib.pop("_last_ma_new_ids", None)
        p = pursuits_store.save(new_lib)
        print(f"[ma] saved -> {p}")

    print(f"[ma] readable diff -> {OUT_DIR / f'ma_diff_{char_id}_{user_id}.txt'}")

    # v3.2 注入模式：返回 MA-END payload 形状
    if return_payload:
        new_lib.pop("_last_ma_new_ids", None)
        accepted = (
            len(decision.get("progress_updates", []))
            + len(decision.get("completed", []))
            + len(decision.get("to_pause", []))
            + len(decision.get("to_revive", []))
            + len(decision.get("new_pursuits", []))
            + len(decision.get("update_estimated_span", []))
            + len(decision.get("update_done_criterion", []))
        )
        diff_summary = (
            f"progress={len(decision.get('progress_updates', []))} "
            f"completed={len(decision.get('completed', []))} "
            f"paused={len(decision.get('to_pause', []))} "
            f"revived={len(decision.get('to_revive', []))} "
            f"new={len(decision.get('new_pursuits', []))} "
            f"upd_span={len(decision.get('update_estimated_span', []))} "
            f"upd_crit={len(decision.get('update_done_criterion', []))}"
        )
        return {
            "new_library": build_new_library_payload(new_lib),
            "accepted_count": accepted,
            "diff_summary": diff_summary,
        }
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--char-id", default="mengya")
    ap.add_argument("--user-id", default="test_user")
    ap.add_argument(
        "--chat",
        default="sandbox/fixtures/chats/mengya_test_user_20260420.json",
        help="对话 transcript JSON",
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff，不回写库")
    args = ap.parse_args(argv)

    chat_path = Path(args.chat)
    if not chat_path.is_absolute():
        chat_path = SANDBOX_ROOT / chat_path

    return run(args.char_id, args.user_id, chat_path, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
