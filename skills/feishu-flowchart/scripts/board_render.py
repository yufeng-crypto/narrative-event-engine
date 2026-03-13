#!/usr/bin/env python3
"""
Render Mermaid flowcharts into Feishu Docx board blocks (editable nodes, not images).

Usage:
  python board_render.py --doc-token <DOC_TOKEN> --mermaid-file flow.mmd
  python board_render.py --doc-token <DOC_TOKEN> --mermaid-text "flowchart TD\nA-->B"

Auth priority:
  1) FEISHU_APP_ID + FEISHU_APP_SECRET env vars
  2) ~/.openclaw/openclaw.json -> channels.feishu.appId/appSecret
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://open.feishu.cn"
TIMEOUT = 30


class FeishuBoardError(RuntimeError):
    pass


def _load_creds() -> tuple[str, str]:
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret

    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        app_id = data.get("channels", {}).get("feishu", {}).get("appId")
        app_secret = data.get("channels", {}).get("feishu", {}).get("appSecret")
        if app_id and app_secret:
            return app_id, app_secret

    raise FeishuBoardError(
        "Missing Feishu credentials. Set FEISHU_APP_ID/FEISHU_APP_SECRET or configure ~/.openclaw/openclaw.json"
    )


def _post_json(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resp = session.post(url, headers=headers, json=payload, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuBoardError(f"API failed: {url} -> {data}")
    return data


def _get_json(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resp = session.get(url, headers=headers, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuBoardError(f"API failed: {url} -> {data}")
    return data


def get_tenant_access_token(session: requests.Session, app_id: str, app_secret: str) -> str:
    resp = session.post(
        f"{BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("tenant_access_token")
    if not token:
        raise FeishuBoardError(f"Failed to get tenant token: {data}")
    return token


def insert_text_block(session: requests.Session, token: str, doc_token: str, text: str) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "children": [
            {
                "block_type": 2,
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": text,
                            }
                        }
                    ]
                },
            }
        ]
    }
    _post_json(
        session,
        f"{BASE_URL}/open-apis/docx/v1/documents/{doc_token}/blocks/{doc_token}/children",
        headers,
        payload,
        params={"document_revision_id": -1},
    )


def insert_board_block(session: requests.Session, token: str, doc_token: str) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"children": [{"block_type": 43, "board": {}}]}
    data = _post_json(
        session,
        f"{BASE_URL}/open-apis/docx/v1/documents/{doc_token}/blocks/{doc_token}/children",
        headers,
        payload,
        params={"document_revision_id": -1},
    )

    try:
        board_token = data["data"]["children"][0]["board"]["token"]
        if board_token:
            return board_token
    except Exception:
        pass

    # fallback: list blocks and find latest board token
    listed = _get_json(
        session,
        f"{BASE_URL}/open-apis/docx/v1/documents/{doc_token}/blocks",
        headers,
        params={"document_revision_id": -1, "page_size": 500},
    )
    for item in reversed(listed.get("data", {}).get("items", [])):
        b = item.get("block", {})
        if b.get("block_type") == 43 and b.get("board", {}).get("token"):
            return b["board"]["token"]

    raise FeishuBoardError("Board block inserted but board.token not found")


def render_mermaid(
    session: requests.Session,
    token: str,
    whiteboard_id: str,
    mermaid_code: str,
    style_type: int = 1,
) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "plant_uml_code": mermaid_code,
        "syntax_type": 2,  # Mermaid
        "style_type": style_type,
        "diagram_type": 0,
    }
    data = _post_json(
        session,
        f"{BASE_URL}/open-apis/board/v1/whiteboards/{whiteboard_id}/nodes/plantuml",
        headers,
        payload,
    )
    return data.get("data", {}).get("node_id", "")


def verify_nodes(session: requests.Session, token: str, whiteboard_id: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    data = _get_json(
        session,
        f"{BASE_URL}/open-apis/board/v1/whiteboards/{whiteboard_id}/nodes",
        headers,
    )
    return len(data.get("data", {}).get("nodes", []))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render Mermaid into Feishu Doc board")
    p.add_argument("--doc-token", required=True, help="Feishu docx token")
    p.add_argument("--mermaid-file", help="Path to Mermaid source file")
    p.add_argument("--mermaid-text", help="Inline Mermaid source text")
    p.add_argument("--title", help="Optional text block inserted before board")
    p.add_argument("--style-type", type=int, default=1, choices=[1, 2])
    p.add_argument("--retry", type=int, default=1, help="Retry times when render fails")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.mermaid_file and not args.mermaid_text:
        raise FeishuBoardError("Provide --mermaid-file or --mermaid-text")

    mermaid = args.mermaid_text
    if args.mermaid_file:
        mermaid = Path(args.mermaid_file).read_text(encoding="utf-8").strip()

    # Normalize escaped newlines from CLI: "\\n" -> real newline
    if mermaid and "\\n" in mermaid:
        mermaid = mermaid.replace("\\n", "\n")

    app_id, app_secret = _load_creds()
    session = requests.Session()
    token = get_tenant_access_token(session, app_id, app_secret)

    if args.title:
        insert_text_block(session, token, args.doc_token, args.title)

    whiteboard_id = insert_board_block(session, token, args.doc_token)

    last_error = None
    style_candidates = [args.style_type] if args.style_type == 2 else [1, 2]

    for style in style_candidates:
        for i in range(args.retry + 1):
            try:
                node_id = render_mermaid(
                    session,
                    token,
                    whiteboard_id,
                    mermaid,
                    style_type=style,
                )
                time.sleep(0.4)
                node_count = verify_nodes(session, token, whiteboard_id)
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "doc_token": args.doc_token,
                            "whiteboard_id": whiteboard_id,
                            "node_id": node_id,
                            "node_count": node_count,
                            "style_type": style,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            except Exception as e:  # noqa: BLE001
                last_error = e
                if i < args.retry:
                    time.sleep(1)
                    continue

    raise FeishuBoardError(f"Render failed after retries/styles: {last_error}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise
