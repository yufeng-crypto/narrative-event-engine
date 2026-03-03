# -*- coding: utf-8 -*-
"""单轮对话测试"""
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))
from engine_llm import Engine

engine = Engine()

# 继续上一次的对话
user_input = "我到了约定的餐厅，给你打电话了，你在哪？"
print(f"\n>>> 用户: {user_input}")
result = engine.run_turn(user_input)
print(f"\n{'='*50}")
print(f"【NPC沈予曦回复】:")
print(result['npc'])
print(f"{'='*50}")
