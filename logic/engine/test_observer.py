# -*- coding: utf-8 -*-
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from engine_llm import get_role_prompt, call_llm

# 测试 Observer
print("=== 测试 Observer ===")
prompt = get_role_prompt("observer")
test_input = {
    "user_input": "刷火箭给你！",
    "npc_output": "哇！火箭！我太开心了！谢谢你！",
    "history": []
}
messages = [
    {"role": "system", "content": prompt[:2000]},
    {"role": "user", "content": f"用户: {test_input['user_input']}\nNPC: {test_input['npc_output']}\n请评估"}
]
result = call_llm(messages)
print("输出:", result[:800])
print("="*50)
print("格式合规:", "json" in result.lower() or "{" in result)
