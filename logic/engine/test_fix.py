# -*- coding: utf-8 -*-
"""用可行的prompt测试"""
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
        
        response = urllib.request.urlopen(req, timeout=15)
        result = json.loads(response.read().decode('utf-8'))
        
        return result.get("choices", [{}])[0].get("message", {}).get("content", "[空]")
        
    except Exception as e:
        return f"[错误] {str(e)[:50]}"

user = "我到了餐厅给你打电话"
axes = "Intimacy=10 Rel=10 Action=8"

print(f"用户: {user}")
print(f"六轴: {axes}")
print("-" * 50)

# Director - 不用JSON
print("\n=== Director ===")
p = f"You are Director. Six axes: {axes}. User: {user}. Tell me the beat and axis changes."
print(f"Prompt: {p[:60]}...")
d = call(p)
print(f"输出: {d[:100]}")

# Performer
print("\n=== Performer ===")
p2 = f"You are Performer. NPC is Shen Yuxi (tsundere). User: {user}. Reply as her."
print(f"Prompt: {p2[:60]}...")
perf = call(p2)
print(f"输出: {perf[:100]}")

print("\n完成")
