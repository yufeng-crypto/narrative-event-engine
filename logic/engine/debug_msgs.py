# -*- coding: utf-8 -*-
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 模拟 engine_llm.py 的调用
CONFIG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
API_KEY = CONFIG.get("api_key", "")
API_URL = CONFIG.get("api_url", "https://api.minimax.chat/v1/text/chatcompletion_v2")
MODEL = CONFIG.get("model", "MiniMax-M2.5")

def call_llm_test(messages):
    import urllib.request
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API_URL, data=data, method='POST')
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode('utf-8'))
    return result

# 测试不同格式
print("=== Test 1: 简单 user 消息 ===")
messages1 = [{"role": "user", "content": "hello"}]
try:
    r = call_llm_test(messages1)
    print("OK:", r.get('choices',[{}])[0].get('message',{}).get('content','')[:50])
except Exception as e:
    print("Error:", e)

print("\n=== Test 2: system + user ===")
messages2 = [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "hello"}
]
try:
    r = call_llm_test(messages2)
    print("OK:", r.get('choices',[{}])[0].get('message',{}).get('content','')[:50])
except Exception as e:
    print("Error:", e)

print("\n=== Test 3: 多个 system + user ===")
messages3 = [
    {"role": "system", "content": "你是Director"},
    {"role": "system", "content": "六轴状态: {\"Intimacy\": 2}"},
    {"role": "user", "content": "用户输入: hello"}
]
try:
    r = call_llm_test(messages3)
    print("Result:", r)
except Exception as e:
    import traceback
    print("Error:", e)
    traceback.print_exc()
