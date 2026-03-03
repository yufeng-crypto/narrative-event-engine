# -*- coding: utf-8 -*-
"""调试 API 调用"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CONFIG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
print("CONFIG:", CONFIG)

API_KEY = CONFIG.get("api_key", "")
API_URL = CONFIG.get("api_url", "")
MODEL = CONFIG.get("model", "MiniMax-M2.5")

print(f"API_URL: {API_URL}")
print(f"MODEL: {MODEL}")

# 测试简单调用
messages = [{"role": "user", "content": "你好"}]

import urllib.request
payload = {
    "model": MODEL,
    "messages": messages
}

print("Payload:", json.dumps(payload, ensure_ascii=False))

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(API_URL, data=data, method='POST')
req.add_header("Authorization", f"Bearer {API_KEY}")
req.add_header("Content-Type", "application/json")

try:
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode('utf-8'))
    print("Result:", result)
except Exception as e:
    print("Error:", e)
