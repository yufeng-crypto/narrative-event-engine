# -*- coding: utf-8 -*-
"""快速测试无引擎调用"""
import sys
import io
import json
import os

# 设置编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

WORKSPACE = r"C:\Users\20731\.openclaw\workspace"
sys.path.insert(0, os.path.join(WORKSPACE, "logic", "engine"))

import engine_llm as eng

# 简单测试
messages = [
    {"role": "system", "content": "你是沈予曦，冷宫妃子。请简洁回复。"},
    {"role": "user", "content": "你好"}
]

result = eng.call_llm(messages)
print("Result:", result[:300])
