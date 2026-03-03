# -*- coding: utf-8 -*-
"""简化版测试"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CONFIG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
API_KEY = CONFIG.get("api_key", "")
URL = CONFIG.get("api_url", "https://api.minimaxi.com/v1/text/chatcompletion_v2")

def call(prompt):
    try:
        import urllib.request
        payload = {"model": "MiniMax-M2.5", "messages": [{"role": "user", "content": prompt}]}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(URL, data=data, method='POST')
        req.add_header("Authorization", "Bearer " + API_KEY)
        req.add_header("Content-Type", "application/json")
        
        resp = urllib.request.urlopen(req, timeout=20)
        result = json.loads(resp.read().decode('utf-8'))
        
        if result.get("base_resp", {}).get("status_code") != 0:
            return f"[API错误] {result.get('base_resp')}"
        
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return f"[OK] {content}" if content else "[空]"
        
    except Exception as e:
        return f"[异常] {e}"

user = "我到了餐厅，给你打电话"
axes = "Intimacy=10 Rel=10 Action=8"

print(f"用户: {user}")
print(f"六轴: {axes}")
print("-" * 40)

# Director
print("\n=== Director ===")
p = f"六轴{axes}。用户{user}。输出JSON beat和axis"
print(f"Prompt: {p[:60]}...")
out = call(p)
print(f"输出: {out}")

# Performer
print("\n=== Performer ===")
p2 = f"你是沈予曦傲娇主播。用户说{user}。请回复"
print(f"Prompt: {p2[:60]}...")
out2 = call(p2)
print(f"输出: {out2}")

print("\n完成")
