# -*- coding: utf-8 -*-
"""调试版 - 显示完整API调用"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_config():
    try:
        return json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    except:
        return {"api_key": "", "model": "MiniMax-M2.5"}

CONFIG = load_config()
API_KEY = CONFIG.get("api_key", "")
URL = CONFIG.get("api_url", "https://api.minimaxi.com/v1/text/chatcompletion_v2")

def call(msgs, label):
    try:
        import urllib.request
        payload = {"model": "MiniMax-M2.5", "messages": msgs}
        data = json.dumps(payload).encode()
        r = urllib.request.Request(URL, data=data, method='POST')
        r.add_header("Authorization", "Bearer " + API_KEY)
        r.add_header("Content-Type", "application/json")
        
        resp = urllib.request.urlopen(r, timeout=25)
        raw = resp.read().decode()
        result = json.loads(raw)
        
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        else:
            return f"[返回空] {raw[:200]}"
    except Exception as e:
        return f"[错误] {e}"

# 简短Prompt
DIRECTOR_P = "你是Director。六轴={}。用户说：{}。输出beat和axis_changes的JSON。"
PREDICTOR_P = "你是Predictor。六轴={}。用户说：{}。输出事件JSON。"
PERFORMER_P = "你是Performer。NPC沈予曦傲娇。用户说：{}。输出对话JSON。"
OBSERVER_P = "你是Observer。评估：用户{} NPC{}。输出JSON。"

axes = {"Intimacy": 10, "Rel": 10, "Action": 8}
user = "我到了餐厅门口，给你打电话"

print(f"\n{'='*50}")
print(f"用户: {user}")
print(f"六轴: {axes}")
print(f"{'='*50}")

# Director
print(f"\n--- Director ---")
msgs = [
    {"role": "system", "content": DIRECTOR_P.format(axes, user)},
    {"role": "user", "content": "请决策"}
]
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:60]}")
d = call(msgs, "Director")
print(f"  >> {d[:80]}")

# Predictor
print(f"\n--- Predictor ---")
msgs = [
    {"role": "system", "content": PREDICTOR_P.format(axes, user)},
    {"role": "user", "content": "请生成事件"}
]
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:60]}")
p = call(msgs, "Predictor")
print(f"  >> {p[:80]}")

# Performer  
print(f"\n--- Performer ---")
msgs = [
    {"role": "system", "content": PERFORMER_P.format(user)},
    {"role": "user", "content": "请回复"}
]
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:60]}")
perf = call(msgs, "Performer")
print(f"  >> {perf[:80]}")

# Observer
print(f"\n--- Observer ---")
msgs = [
    {"role": "system", "content": OBSERVER_P.format(user, perf[:30])},
    {"role": "user", "content": "请评估"}
]
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:60]}")
obs = call(msgs, "Observer")
print(f"  >> {obs[:80]}")

print(f"\n{'='*50}")
print("完成")
