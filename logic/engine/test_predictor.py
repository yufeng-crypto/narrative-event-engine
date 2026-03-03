# -*- coding: utf-8 -*-
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from engine_llm import Engine, get_role_prompt, call_llm

# 测试 Predictor
print("=== 测试 Predictor ===")
prompt = get_role_prompt("predictor")
test_input = {
    "user_input": "刷火箭给你！",
    "axes": {"Intimacy": 5, "Risk": 3, "Info": 4, "Action": 5, "Rel": 1, "Growth": 7},
    "director_output": {"beat": "EVOLVE", "axis_changes": {"Intimacy": 1}}
}
messages = [
    {"role": "system", "content": prompt[:2000]},
    {"role": "user", "content": f"用户输入: {test_input['user_input']}\n六轴: {json.dumps(test_input['axes'])}\nDirector决策: {json.dumps(test_input['director_output'])}\n请生成事件卡"}
]
result = call_llm(messages)
print("输出:", result[:500])
print("格式合规:", "json" in result.lower() or "{" in result)
