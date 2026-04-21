# -*- coding: utf-8 -*-
"""pursuits v3.2 中控注入/回调适配器。

沙盒原路径（Phase 0）：`pursuits_store.load(char, user)` 读本地 fixture，
`pursuits_store.save(lib)` 写本地 fixture。

v3.2 正式架构（见 `sandbox_notes/pursuits_midcontrol_integration_v3.md`）：
- **读**：中控从 DB 查出 `pursuits_library.pursuits_json`，序列化成字符串后
  通过 `sys.pursuits_library` 注入到 Dify start；工作流内部节点 CS-01 / MA-01 /
  MB-01 解析字符串。空库时中控 **必须** 注入 `""` 或 `"null"`（不允许漏传）。
- **写**：工作流 END 节点输出 `new_library` 字符串（单次 JSON.stringify；Dify
  本身还会再套一层，形成双重编码 —— 见 `feedback_dify_encoding.md`）。中控解析
  后 `upsert pursuits_library (char_id, user_id)`，只写 `pursuits_json` +
  `updated_at` 两列。

本模块只管这层协议，不碰 LLM / 不碰 prompt / 不碰 pursuit schema 细节。

使用方式
--------

1) 解析注入字符串（模拟 CS-01 / MA-01 / MB-01 起手那段 CODE）::

    lib = parse_injected_library(raw, char_id="mengya", user_id="test_user")
    # raw 可以是 "" / "null" / None / 已 parse 的 dict / JSON 字符串

2) 拼 END 回调 payload（模拟三个工作流的 END 节点输出 new_library）::

    payload = build_new_library_payload(new_lib)
    # -> {"char_id": ..., "user_id": ..., "pursuits": [...], "updated_at": "..."}
    s = serialize_new_library(new_lib)
    # -> JSON 字符串（单次 stringify；Dify 会再编一层）
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Union

IdType = Union[str, int]

# 中控约定的空库哨兵值。实际使用时 `""` 和 `"null"` 等价，都表示"查 DB 没有这行"。
_EMPTY_SENTINELS = {"", "null", "None"}


def _empty_library(char_id: IdType, user_id: IdType, now_iso: str | None = None) -> dict:
    """构造一个形状合法、内容为空的库对象（CS-01 if-else lib_empty 分支之后的状态）。

    字段与 `pursuits_store.new_library` 保持一致，但 `last_cold_start_at=None` 表示
    这一步 *还没* 冷启动（注入的就是空库；CS-03 LLM 之后才会被填）。
    """
    now_iso = now_iso or datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "char_id": char_id,
        "user_id": user_id,
        "version": 1,
        "last_cold_start_at": None,
        "last_maintenance_at": None,
        "active_count": 0,
        "done_count": 0,
        "dropped_count": 0,
        "paused_count": 0,
        "pursuits_top5_cache": [],
        "pursuits": [],
    }


def parse_injected_library(
    raw: Any,
    char_id: IdType,
    user_id: IdType,
    *,
    strict: bool = False,
) -> dict:
    """解析 mid-control 注入的 `sys.pursuits_library` 字符串。

    三种情况：
    1. 空库（`""` / `"null"` / `None`）       → 返回 `_empty_library(...)`
    2. 已 parse 的 dict（本地 fixture 路径）  → 原样返回（仅补 char_id / user_id 校验）
    3. JSON 字符串                            → `json.loads` 后返回；必填字段校验

    Parameters
    ----------
    raw : 注入字符串或已解析的 dict；None/空视作空库
    char_id, user_id : 必填；用来和 raw 里的字段做一致性校验
    strict : True 时，JSON 解析失败会 raise；默认 False，静默回退到空库并打 warning

    Returns
    -------
    dict : 规范化后的 library 对象，保证有 `char_id` / `user_id` / `pursuits`

    Raises
    ------
    ValueError : strict=True 时，JSON 解析失败 / dict 结构非法 / char_id 不一致
    """
    # 1) 空库判定
    if raw is None:
        return _empty_library(char_id, user_id)
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped in _EMPTY_SENTINELS:
            return _empty_library(char_id, user_id)
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as e:
            if strict:
                raise ValueError(
                    f"pursuits_library 注入字符串不是合法 JSON（也不是空哨兵）: "
                    f"{stripped[:80]!r} ({e})"
                ) from e
            # 非 strict：当成空库，防止中控漏传导致工作流崩
            return _empty_library(char_id, user_id)
    elif isinstance(raw, dict):
        obj = raw
    else:
        if strict:
            raise ValueError(
                f"pursuits_library 注入值类型不支持: {type(raw).__name__}"
            )
        return _empty_library(char_id, user_id)

    # 2) 结构校验
    if not isinstance(obj, dict):
        if strict:
            raise ValueError(
                f"pursuits_library 解析后不是 JSON 对象而是 {type(obj).__name__}"
            )
        return _empty_library(char_id, user_id)

    # 3) 一致性校验（char_id / user_id 允许 str/int 混用：做 str() 后对比）
    obj_char = obj.get("char_id")
    obj_user = obj.get("user_id")
    if obj_char is not None and str(obj_char) != str(char_id):
        if strict:
            raise ValueError(
                f"pursuits_library.char_id={obj_char!r} 与注入参数 {char_id!r} 不一致"
            )
    if obj_user is not None and str(obj_user) != str(user_id):
        if strict:
            raise ValueError(
                f"pursuits_library.user_id={obj_user!r} 与注入参数 {user_id!r} 不一致"
            )

    # 4) 补全缺失字段（老库可能没这些字段；防止后续 KeyError）
    obj.setdefault("char_id", char_id)
    obj.setdefault("user_id", user_id)
    obj.setdefault("pursuits", [])
    if not isinstance(obj.get("pursuits"), list):
        if strict:
            raise ValueError("pursuits 字段必须是数组")
        obj["pursuits"] = []
    obj.setdefault("active_count", sum(1 for p in obj["pursuits"] if p.get("status") == "active"))
    obj.setdefault("done_count", sum(1 for p in obj["pursuits"] if p.get("status") == "done"))
    obj.setdefault("dropped_count", sum(1 for p in obj["pursuits"] if p.get("status") == "dropped"))
    obj.setdefault("paused_count", sum(1 for p in obj["pursuits"] if p.get("status") == "paused"))
    obj.setdefault("pursuits_top5_cache", [])
    obj.setdefault("version", 1)
    obj.setdefault("last_cold_start_at", None)
    obj.setdefault("last_maintenance_at", None)

    return obj


def build_new_library_payload(lib: dict) -> dict:
    """从完整 lib 对象中抽出 END 回调给 mid-control 的 4 字段 payload。

    对应 `pursuits_midcontrol_integration_v3.md §2` 的 `new_library` 形状：

        {
          "char_id": 123,
          "user_id": 456,
          "pursuits": [...],
          "updated_at": "2026-04-21T..."
        }

    `pursuits_top5_cache` 不在 payload 里（那是 Redis 的事；中控不碰）。
    `active_count / done_count / ...` 也不在 payload 里（中控可以根据 pursuits 数组
    自己算；不需要来回传）。

    Parameters
    ----------
    lib : 完整库对象（从 apply_changes / normalize_and_dedupe 出来的形态）

    Returns
    -------
    dict : 形状固定的 4 字段对象，随时可以 `json.dumps` 成字符串
    """
    updated_at = lib.get("updated_at") or datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "char_id": lib.get("char_id"),
        "user_id": lib.get("user_id"),
        "pursuits": lib.get("pursuits", []),
        "updated_at": updated_at,
    }


def serialize_new_library(lib: dict, *, ensure_ascii: bool = False) -> str:
    """把 lib 直接序列化成 END 节点要输出的字符串形态（单次 JSON.stringify）。

    Dify 会再 stringify 一层（双重编码，见 `feedback_dify_encoding.md`），
    但那层是 workflow runtime 的事，沙盒这边只管第一层。
    """
    payload = build_new_library_payload(lib)
    return json.dumps(payload, ensure_ascii=ensure_ascii, separators=(",", ":"))


# ---------- 反向：给 sandbox e2e 测试用（模拟 mid-control 读取 payload） ----------

def parse_end_payload(payload_str: str, *, double_encoded: bool = False) -> dict:
    """解析 END 节点输出的 `new_library` 字符串。

    - `double_encoded=False`：单次 JSON.parse（沙盒内部调用常用此路径）
    - `double_encoded=True`：两次 JSON.parse（模拟 Dify 真实行为）

    返回 4 字段 payload dict（char_id / user_id / pursuits / updated_at）。
    """
    s = payload_str
    if double_encoded:
        s = json.loads(s)
        if not isinstance(s, str):
            raise ValueError("double_encoded=True 时外层必须 parse 出字符串")
    return json.loads(s)
