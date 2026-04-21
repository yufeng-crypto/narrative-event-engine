# -*- coding: utf-8 -*-
"""pursuits v3.2 注入/回调适配器的回归测试。

锁死以下协议（`sandbox_notes/pursuits_midcontrol_integration_v3.md`）：
- 空库三态（"" / "null" / None）等价 → 空库对象
- JSON 字符串正确解析 + 缺字段补全
- build_new_library_payload 只出 4 字段
- 单次 vs 双重 JSON 编码的 parse_end_payload
- char_id / user_id 一致性（strict 模式）

跑法：`pytest sandbox/tests/test_pursuits_v32_adapter.py -q`
"""
from __future__ import annotations

import json

import pytest

from sandbox.services.pursuits_v32_adapter import (
    build_new_library_payload,
    parse_end_payload,
    parse_injected_library,
    serialize_new_library,
)


# ============================================================================
# T_empty: 空库三态（中控漏查/查不到时的注入形态）
# ============================================================================

@pytest.mark.parametrize("raw", ["", "null", "None", None])
def test_empty_sentinels_yield_empty_library(raw):
    lib = parse_injected_library(raw, char_id="mengya", user_id="test_user")
    assert lib["char_id"] == "mengya"
    assert lib["user_id"] == "test_user"
    assert lib["pursuits"] == []
    assert lib["active_count"] == 0
    assert lib["done_count"] == 0
    assert lib["dropped_count"] == 0
    assert lib["paused_count"] == 0
    assert lib["pursuits_top5_cache"] == []
    # last_cold_start_at = None：表示 CS-01 之后进 lib_empty 分支，还没建库
    assert lib["last_cold_start_at"] is None


def test_empty_library_schema_stable():
    """空库字段名不能悄悄改（CS-04 / MA-01 / MB-01 代码里按字段名读）。"""
    lib = parse_injected_library("", char_id=1, user_id=2)
    required = {
        "char_id", "user_id", "version",
        "last_cold_start_at", "last_maintenance_at",
        "active_count", "done_count", "dropped_count", "paused_count",
        "pursuits_top5_cache", "pursuits",
    }
    assert required.issubset(lib.keys())


# ============================================================================
# T_parse: 注入的是 JSON 字符串
# ============================================================================

def _sample_lib_json(char_id="mengya", user_id="test_user") -> str:
    obj = {
        "char_id": char_id,
        "user_id": user_id,
        "version": 1,
        "last_cold_start_at": "2026-04-20T10:00:00+08:00",
        "last_maintenance_at": None,
        "active_count": 2,
        "done_count": 1,
        "dropped_count": 0,
        "pursuits_top5_cache": [],
        "pursuits": [
            {"id": "pur_20260420_001", "title": "测试目标1", "status": "active"},
            {"id": "pur_20260420_002", "title": "测试目标2", "status": "active"},
            {"id": "pur_20260420_003", "title": "测试目标3", "status": "done"},
        ],
    }
    return json.dumps(obj, ensure_ascii=False)


def test_parse_json_string_roundtrip():
    raw = _sample_lib_json()
    lib = parse_injected_library(raw, char_id="mengya", user_id="test_user")
    assert lib["char_id"] == "mengya"
    assert len(lib["pursuits"]) == 3
    assert lib["active_count"] == 2
    assert lib["done_count"] == 1


def test_parse_dict_passthrough():
    """已 parse 成 dict 的（沙盒 fixture 路径）也应该接受。"""
    raw = json.loads(_sample_lib_json())
    lib = parse_injected_library(raw, char_id="mengya", user_id="test_user")
    assert lib["pursuits"][0]["id"] == "pur_20260420_001"


def test_parse_json_recomputes_missing_counts():
    """老库或缩水的 payload 里缺 count 字段时，应从 pursuits 数组里算出。"""
    obj = {
        "char_id": "x",
        "user_id": "y",
        "pursuits": [
            {"id": "a", "status": "active"},
            {"id": "b", "status": "active"},
            {"id": "c", "status": "paused"},
            {"id": "d", "status": "done"},
        ],
        # 故意没填 active_count / done_count / paused_count / dropped_count
    }
    lib = parse_injected_library(json.dumps(obj), char_id="x", user_id="y")
    assert lib["active_count"] == 2
    assert lib["done_count"] == 1
    assert lib["paused_count"] == 1
    assert lib["dropped_count"] == 0


# ============================================================================
# T_id: char_id / user_id 一致性校验
# ============================================================================

def test_id_type_mixing_ok_when_string_equal():
    """沙盒 str 名义 id / 线上 int 数字 id 允许混用，只要 str() 后相等。"""
    obj = {"char_id": 592, "user_id": 839, "pursuits": []}
    lib = parse_injected_library(json.dumps(obj), char_id="592", user_id="839")
    assert lib["char_id"] == 592  # 保留 raw 里原值


def test_id_mismatch_non_strict_silent():
    obj = {"char_id": "alice", "user_id": "bob", "pursuits": []}
    lib = parse_injected_library(json.dumps(obj), char_id="mengya", user_id="test_user")
    # 非 strict：不 raise；上层决定怎么处理（埋点 / 兜底 / 丢弃）
    assert lib["char_id"] == "alice"  # 保留 raw


def test_id_mismatch_strict_raises():
    obj = {"char_id": "alice", "user_id": "bob", "pursuits": []}
    with pytest.raises(ValueError, match="char_id"):
        parse_injected_library(
            json.dumps(obj), char_id="mengya", user_id="test_user", strict=True
        )


# ============================================================================
# T_robustness: 坏数据兜底（非 strict 不 raise；strict raise）
# ============================================================================

def test_invalid_json_non_strict_yields_empty():
    lib = parse_injected_library("this is not json {", char_id="x", user_id="y")
    assert lib["pursuits"] == []  # 兜底到空库


def test_invalid_json_strict_raises():
    with pytest.raises(ValueError, match="JSON"):
        parse_injected_library(
            "this is not json {", char_id="x", user_id="y", strict=True
        )


def test_wrong_type_non_strict_yields_empty():
    """注入值不是 str/dict/None（比如误传了数字）—— 非 strict 兜底空库。"""
    lib = parse_injected_library(42, char_id="x", user_id="y")
    assert lib["pursuits"] == []


def test_pursuits_not_array_non_strict():
    """pursuits 字段被注入成非数组时，非 strict 应兜底成 []。"""
    obj = {"char_id": "x", "user_id": "y", "pursuits": "oops"}
    lib = parse_injected_library(json.dumps(obj), char_id="x", user_id="y")
    assert lib["pursuits"] == []


def test_pursuits_not_array_strict_raises():
    obj = {"char_id": "x", "user_id": "y", "pursuits": "oops"}
    with pytest.raises(ValueError, match="pursuits"):
        parse_injected_library(
            json.dumps(obj), char_id="x", user_id="y", strict=True
        )


# ============================================================================
# T_payload: END 回调 new_library 的 4 字段 payload
# ============================================================================

def test_build_new_library_payload_shape():
    lib = {
        "char_id": "mengya",
        "user_id": "test_user",
        "version": 1,
        "updated_at": "2026-04-21T10:00:00+08:00",
        "active_count": 2,
        "done_count": 1,
        "pursuits_top5_cache": [{"id": "x"}],  # 不应出现在 payload 里
        "pursuits": [
            {"id": "pur_1", "title": "t1", "status": "active"},
        ],
    }
    payload = build_new_library_payload(lib)
    # 只有 4 个 key
    assert set(payload.keys()) == {"char_id", "user_id", "pursuits", "updated_at"}
    assert payload["char_id"] == "mengya"
    assert payload["user_id"] == "test_user"
    assert len(payload["pursuits"]) == 1
    assert payload["updated_at"] == "2026-04-21T10:00:00+08:00"


def test_build_new_library_payload_generates_updated_at_if_missing():
    lib = {"char_id": "x", "user_id": "y", "pursuits": []}
    payload = build_new_library_payload(lib)
    assert payload["updated_at"]  # 非空


def test_payload_excludes_top5_and_counts():
    """top5 / 计数类字段不进 payload（Redis 的事 / 中控可重算）。"""
    lib = {
        "char_id": "x",
        "user_id": "y",
        "active_count": 5,
        "done_count": 3,
        "pursuits_top5_cache": [{"id": "a"}],
        "last_maintenance_at": "2026-04-21T00:00:00",
        "pursuits": [],
    }
    payload = build_new_library_payload(lib)
    assert "active_count" not in payload
    assert "done_count" not in payload
    assert "pursuits_top5_cache" not in payload
    assert "last_maintenance_at" not in payload


# ============================================================================
# T_serialize: END 节点输出字符串形态 + 双重编码兜底
# ============================================================================

def test_serialize_single_encoding_roundtrip():
    lib = {
        "char_id": "mengya",
        "user_id": "test_user",
        "pursuits": [{"id": "pur_1", "title": "目标1"}],
    }
    s = serialize_new_library(lib)
    assert isinstance(s, str)
    # 单次 parse 回来
    obj = parse_end_payload(s)
    assert obj["char_id"] == "mengya"
    assert obj["pursuits"][0]["title"] == "目标1"


def test_serialize_ascii_off_keeps_chinese():
    """ensure_ascii=False（默认）—— 中文不要被 \\uXXXX 转义。"""
    lib = {"char_id": "x", "user_id": "y", "pursuits": [{"title": "测试"}]}
    s = serialize_new_library(lib)
    assert "测试" in s  # 原文中文保留


def test_parse_end_payload_double_encoded():
    """Dify END 节点实际输出是双重编码字符串：先 stringify 1 层，Dify 再套 1 层。"""
    lib = {"char_id": "x", "user_id": "y", "pursuits": []}
    inner = serialize_new_library(lib)  # 单层
    outer = json.dumps(inner)  # 套第二层（模拟 Dify 行为）
    obj = parse_end_payload(outer, double_encoded=True)
    assert obj["char_id"] == "x"
    assert obj["pursuits"] == []


def test_parse_end_payload_double_encoded_raises_if_not_string_inside():
    """声明了 double_encoded=True 但外层其实是个 dict —— 应该报错而不是静默 parse 错。"""
    raw = json.dumps({"char_id": "x", "user_id": "y", "pursuits": []})
    with pytest.raises(ValueError, match="字符串"):
        parse_end_payload(raw, double_encoded=True)
