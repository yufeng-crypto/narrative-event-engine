# -*- coding: utf-8 -*-
"""简化版 - 每个角色只传1个system消息"""
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

def call(msgs):
    try:
        import urllib.request
        data = json.dumps({"model": "MiniMax-M2.5", "messages": msgs, "max_completion_tokens": 500}).encode()
        r = urllib.request.Request(URL, data=data, method='POST')
        r.add_header("Authorization", "Bearer " + API_KEY)
        r.add_header("Content-Type", "application/json")
        result = json.loads(urllib.request.urlopen(r, timeout=25).read().decode())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[ERROR: {e}]"

# Prompt模板 (简短版)
DIRECTOR_SYS = "你是Director。根据六轴和用户输入，输出JSON：{\"beat\": \"HOLD|EVOLVE\", \"axis_changes\": {}, \"reason\": \"\"}"
PREDICTOR_SYS = "你是Predictor。生成事件卡，输出JSON：{\"events\": [{\"title\": \"\", \"hook\": \"\"}]}"
PERFORMER_SYS = "你是Performer。生成对话，输出JSON：{\"reply\": \"\", \"emotion\": \"\"}"
OBSERVER_SYS = "你是Observer。评估，输出JSON：{\"score\": 1, \"note\": \"\"}"

# 状态
axes = {"Intimacy": 10, "Rel": 10, "Action": 8, "Risk": 5, "Info": 9, "Growth": 9}
history = []

user = "我到了约定的餐厅，拨通了沈予曦的电话"

print(f"\n{'#'*60}")
print(f"用户: {user}")
print(f"六轴: {json.dumps(axes)}")
print(f"{'#'*60}")

# Director
print(f"\n=== Director ===")
msgs = [
    {"role": "system", "content": DIRECTOR_SYS},
    {"role": "system", "content": f"六轴: {axes}"},
    {"role": "system", "content": f"历史: {history}"},
    {"role": "user", "content": user}
]
print("【传入messages】")
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:50]}...")
d_out = call(msgs)
print(f"【输出】: {d_out[:100]}")

# Predictor  
print(f"\n=== Predictor ===")
msgs = [
    {"role": "system", "content": PREDICTOR_SYS},
    {"role": "system", "content": f"六轴: {axes}"},
    {"role": "system", "content": f"Director: {d_out[:100]}"},
    {"role": "user", "content": user}
]
print("【传入messages】")
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:50]}...")
p_out = call(msgs)
print(f"【输出】: {p_out[:100]}")

# Performer
print(f"\n=== Performer ===")
msgs = [
    {"role": "system", "content": PERFORMER_SYS},
    {"role": "system", "content": f"六轴: {axes}"},
    {"role": "system", "content": f"NPC: 沈予曦傲娇"},
    {"role": "system", "content": f"决策: {d_out[:50]}"},
    {"role": "user", "content": user}
]
print("【传入messages】")
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:50]}...")
perf_out = call(msgs)
print(f"【输出】: {perf_out[:100]}")

# Observer
print(f"\n=== Observer ===")
msgs = [
    {"role": "system", "content": OBSERVER_SYS},
    {"role": "system", "content": f"历史: {history}"},
    {"role": "user", "content": f"用户:{user} NPC:{perf_out[:50]}"}
]
print("【传入messages】")
for i,m in enumerate(msgs): print(f"  [{i}] {m['role']}: {m['content'][:50]}...")
obs_out = call(msgs)
print(f"【输出】: {obs_out[:100]}")

print(f"\n完成")
