# -*- coding: utf-8 -*-
"""交互式对话测试 - 继续上一次的对话"""
import sys
import io
import json
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 导入 engine_llm
sys.path.insert(0, os.path.dirname(__file__))
from engine_llm import Engine

def main():
    print("=" * 60)
    print("【爱巴基斯坦叙事引擎 - 交互式对话】")
    print("场景：我到了约定的餐厅，拨通了沈予曦的电话")
    print("=" * 60)
    
    engine = Engine()
    
    # 第一轮：用户到了餐厅打电话
    first_input = "我到了约定的餐厅，给你打电话了，你在哪？"
    print(f"\n>>> 用户: {first_input}")
    result = engine.run_turn(first_input)
    print(f"\n【NPC沈予曦】: {result['npc'][:200]}...")
    
    print("\n" + "=" * 60)
    print("请继续输入对话（输入 q 退出）:")
    print("=" * 60)
    
    while True:
        try:
            user_input = input("\n>>> 用户: ").strip()
            if user_input.lower() == 'q':
                break
            if not user_input:
                continue
            
            result = engine.run_turn(user_input)
            print(f"\n【NPC沈予曦】: {result['npc'][:300]}...")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[错误] {e}")
    
    print("\n对话结束")

if __name__ == "__main__":
    main()
