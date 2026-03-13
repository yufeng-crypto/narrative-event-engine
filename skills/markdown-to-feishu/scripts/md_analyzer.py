#!/usr/bin/env python3
"""
Markdown 文档分析工具：提取 Heading、代码块、表格、流程图供飞书转换使用。

Usage:
  python md_analyzer.py <input.md> [--output json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def extract_headings(content: str) -> list[dict[str, Any]]:
    """提取所有 Heading 及其层级"""
    headings = []

    # 方式1: # 语法
    for i, line in enumerate(content.split("\n"), 1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            headings.append({
                "level": len(match.group(1)),
                "text": match.group(2).strip(),
                "line": i
            })

    # 方式2: **加粗** 语法（如 **一、设计背景与目标**）
    for i, line in enumerate(content.split("\n"), 1):
        match = re.match(r"^\*\*(.+)\*\*$", line.strip())
        if match:
            text = match.group(1).strip()
            # 提取章节编号
            level = 1
            if text.startswith("一、") or text.startswith("二、") or text.startswith("三、") or \
               text.startswith("四、") or text.startswith("五、") or text.startswith("六、"):
                level = 1
            elif re.match(r"^\d+\.", text):
                level = 2
            elif text.startswith("v1."):
                continue  # 版本信息跳过
            headings.append({
                "level": level,
                "text": text,
                "line": i
            })

    return headings


def extract_code_blocks(content: str) -> list[dict[str, Any]]:
    """提取所有代码块"""
    blocks = []
    pattern = r"```(\w+)?\n(.*?)```"
    for match in re.finditer(pattern, content, re.DOTALL):
        lang = match.group(1) or "text"
        code = match.group(2).strip()
        blocks.append({
            "language": lang,
            "code": code,
            "start": match.start(),
            "end": match.end()
        })
    return blocks


def extract_tables(content: str) -> list[dict[str, Any]]:
    """提取 ASCII 表格（| 格式）"""
    tables = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and "|" in line[1:]:
            # 开始一个表格
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [cell.strip() for cell in lines[i].strip().split("|")[1:-1]]
                rows.append(row)
                i += 1
            # 跳过分隔行（---）
            if i < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i].strip()):
                i += 1
            if rows:
                tables.append({"rows": rows, "start_line": i - len(rows)})
        else:
            i += 1
    return tables


def extract_flowcharts(content: str) -> list[dict[str, Any]]:
    """提取流程图内容（Mermaid 或文字版）"""
    flowcharts = []

    # 1. Mermaid 代码块
    pattern = r"```mermaid\n(.*?)```"
    for match in re.finditer(pattern, content, re.DOTALL):
        flowcharts.append({
            "type": "mermaid",
            "content": match.group(1).strip(),
            "start": match.start(),
            "end": match.end()
        })

    # 2. 流程图关键词段落
    keywords = ["流程图", "数据流", "工作流", "节点流向", "时序图"]
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if any(kw in line for kw in keywords):
            # 尝试提取下方文字版流程
            context = "\n".join(lines[i:min(i+30, len(lines))])
            if "→" in context or "↓" in context or "├──" in context:
                flowcharts.append({
                    "type": "text",
                    "content": context[:500],  # 截取前500字符
                    "line": i + 1
                })

    return flowcharts


def analyze_markdown(file_path: str) -> dict[str, Any]:
    """完整分析 Markdown 文件"""
    content = Path(file_path).read_text(encoding="utf-8")

    return {
        "file": file_path,
        "headings": extract_headings(content),
        "code_blocks": extract_code_blocks(content),
        "tables": extract_tables(content),
        "flowcharts": extract_flowcharts(content),
        "stats": {
            "total_lines": len(content.split("\n")),
            "total_chars": len(content),
            "heading_count": len(extract_headings(content)),
            "code_block_count": len(extract_code_blocks(content)),
            "table_count": len(extract_tables(content)),
            "flowchart_count": len(extract_flowcharts(content))
        }
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze Markdown for Feishu conversion")
    p.add_argument("input", help="Input Markdown file")
    p.add_argument("--output", choices=["json", "summary"], default="summary")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    result = analyze_markdown(args.input)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[FILE] {result['file']}")
        print(f"[LINES] {result['stats']['total_lines']}")
        print(f"[HEADINGS] {result['stats']['heading_count']}")
        print(f"[CODE_BLOCKS] {result['stats']['code_block_count']}")
        print(f"[TABLES] {result['stats']['table_count']}")
        print(f"[FLOWCHARTS] {result['stats']['flowchart_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
