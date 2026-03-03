# -*- coding: utf-8 -*-
"""测试引擎基本功能"""
import sys
sys.path.insert(0, r'C:\Users\20731\.openclaw\workspace\logic\engine')
from engine_llm import Engine, create_engine, start_engine, chat

print("测试1: 创建引擎")
e = create_engine()
print("  OK")

print("测试2: 初始化引擎")
result = start_engine(e, 'shenyuxi', '测试角色')
scene = result.get('scene_archive', '')
print(f"  OK, scene: {scene[:30]}...")

print("测试3: 对话")
result = chat(e, '你好')
reply = result.get('npc', '')
print(f"  OK, reply: {reply[:50]}...")

print("\n所有基本测试通过!")
