# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from engine_llm import Engine

engine = Engine()
user_input = "我到了约定的餐厅，给你打电话了，你在哪？"
print(f"\n>>> 用户: {user_input}")
result = engine.run_turn(user_input)
print("="*50)
print("【NPC沈予曦回复】:")
print(result['npc'])
print("="*50)
