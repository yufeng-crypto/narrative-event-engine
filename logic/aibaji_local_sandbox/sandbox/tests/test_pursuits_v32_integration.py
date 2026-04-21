# -*- coding: utf-8 -*-
"""pursuits v3.2 注入模式 —— 三个模拟器 run() 入口的契约测试。

只覆盖 **不跑 LLM 的分支**（空库 / 已有库跳过）：
- CS：注入非空库 → skip payload
- CS：注入空库 → 走 LLM 路径（这里不测，只 mock 化）
- MA：注入空库 → no-op payload
- MB：注入空库 → no-op payload

真跑 LLM 的 e2e 回归留给 pursuits_probe / quality-test 手跑；这里只锁死
"契约层"：run(return_payload=True) 的返回值形状必须匹配
mid-control 三个 END 的约定（见 pursuits_midcontrol_integration_v3.md §2）。

跑法：`pytest sandbox/tests/test_pursuits_v32_integration.py -q`
"""
from __future__ import annotations

import json
from pathlib import Path

from sandbox.tools import (
    pursuits_cold_start,
    pursuits_maintain_after_chat,
    pursuits_maintain_after_schedule,
)


# ============================================================================
# CS：注入非空库 → 走 CS-END-skip 分支
# ============================================================================

def test_cs_skip_when_library_nonempty():
    raw = json.dumps({
        "char_id": "mengya",
        "user_id": "test_user",
        "pursuits": [{"id": "pur_1", "title": "已有目标", "status": "active"}],
    })
    result = pursuits_cold_start.run(
        "mengya", "test_user",
        pursuits_library_raw=raw,
        return_payload=True,
    )
    # 形状必须是 CS-END-skip 约定
    assert isinstance(result, dict)
    assert result["skipped"] == "true"
    assert "already exists" in result["reason"]
    assert result["accepted_count"] == 0
    # 不应带 new_library（skip 分支不回写）
    assert "new_library" not in result


def test_cs_skip_returns_int_in_legacy_mode():
    """老路径向后兼容：return_payload=False 时返回 int。"""
    raw = json.dumps({
        "char_id": "x", "user_id": "y",
        "pursuits": [{"id": "a", "status": "active"}],
    })
    result = pursuits_cold_start.run(
        "x", "y",
        pursuits_library_raw=raw,
        return_payload=False,
    )
    assert isinstance(result, int)
    assert result == 2  # skip exit code


# ============================================================================
# MA：注入空库 → no-op MA-END payload
# ============================================================================

def test_ma_noop_on_empty_injection():
    # chat_path 不用存在 —— 空库分支会在 load_chat 之前 return
    dummy_chat = Path("/tmp/nonexistent_chat.json")
    result = pursuits_maintain_after_chat.run(
        "mengya", "test_user",
        chat_path=dummy_chat,
        pursuits_library_raw="",
        return_payload=True,
    )
    # MA-END no-op payload 约定形状
    assert isinstance(result, dict)
    assert set(result.keys()) == {"new_library", "accepted_count", "diff_summary"}
    assert result["accepted_count"] == 0
    assert result["new_library"]["pursuits"] == []
    assert "progress=0" in result["diff_summary"]
    assert "new=0" in result["diff_summary"]


def test_ma_noop_null_sentinel():
    """'null' 哨兵同样触发 no-op。"""
    dummy_chat = Path("/tmp/nonexistent_chat.json")
    result = pursuits_maintain_after_chat.run(
        "x", "y",
        chat_path=dummy_chat,
        pursuits_library_raw="null",
        return_payload=True,
    )
    assert result["new_library"]["pursuits"] == []


# ============================================================================
# MB：注入空库 → no-op MB-END payload
# ============================================================================

def test_mb_noop_on_empty_injection():
    result = pursuits_maintain_after_schedule.run(
        "mengya", "test_user",
        pursuits_library_raw="",
        return_payload=True,
    )
    # MB-END no-op payload 约定形状
    assert isinstance(result, dict)
    assert set(result.keys()) == {"new_library", "accepted_count", "auto_paused_summary"}
    assert result["accepted_count"] == 0
    assert result["new_library"]["pursuits"] == []
    assert "auto_paused=0" in result["auto_paused_summary"]


def test_mb_noop_null_sentinel():
    result = pursuits_maintain_after_schedule.run(
        "x", "y",
        pursuits_library_raw="null",
        return_payload=True,
    )
    assert result["new_library"]["pursuits"] == []


# ============================================================================
# 三个 payload 的 new_library 都是 4 字段形状（不泄漏内部状态字段）
# ============================================================================

def _assert_new_library_is_4_fields(payload: dict):
    """new_library payload 严格 4 字段（char_id / user_id / pursuits / updated_at）。"""
    assert set(payload.keys()) == {"char_id", "user_id", "pursuits", "updated_at"}


def test_ma_new_library_shape_strict():
    dummy_chat = Path("/tmp/nonexistent_chat.json")
    result = pursuits_maintain_after_chat.run(
        "x", "y",
        chat_path=dummy_chat,
        pursuits_library_raw="",
        return_payload=True,
    )
    _assert_new_library_is_4_fields(result["new_library"])


def test_mb_new_library_shape_strict():
    result = pursuits_maintain_after_schedule.run(
        "x", "y",
        pursuits_library_raw="",
        return_payload=True,
    )
    _assert_new_library_is_4_fields(result["new_library"])
