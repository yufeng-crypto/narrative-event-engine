# -*- coding: utf-8 -*-
"""实际运行测试 - 详细错误信息"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CONFIG = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
API_KEY = CONFIG.get("api_key", "")
URL = CONFIG.get("api_url", "https://api.minimaxi.com/v1/text/chatcompletion_v2")

def call_llm(messages, label):
    try:
        import urllib.request
        payload = {"model": "MiniMax-M2.5", "messages": messages, "max_completion_tokens": 200}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(URL, data=data, method='POST')
        req.add_header("Authorization", "Bearer " + API_KEY)
        req.add_header("Content-Type", "application/json")
        
        response = urllib.request.urlopen(req, timeout=20)
        result = json.loads(response.read().decode('utf-8'))
        
        # 检查API返回
        if result.get("base_resp", {}).get("status_code") != 0:
            return f"[API错误] {result.get('base_resp')}"
        
        choices = result.get("choices")
        if not choices:
            return f"[返回空] {result}"
        
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            return f"[内容空] {result}"
        
        return f"[OK] {content[:200]}"
        
    except Exception as e:
        return f"[异常] {type(e).__name__}: {str(e)[:80]}"

# 状态
axes = {"Intimacy": 10, "Rel": 10, "Action": 8, "Risk": 5, "Info": 9, "Growth": 9}
user = "我到了约定的餐厅，拨通了沈予曦的电话"

print(f"\n{'='*60}")
print(f"用户输入: {user}")
print(f"六轴: {axes}")
print(f"{'='*60}\n")

# Director
print("=== Director ===")
print("【传入messages】")
msgs = [
    {"role": "system", "content": "你是Director。输出JSON：beat和axis_changes"},
    {"role": "system", "content": f"六轴: {json.dumps(axes)}"},
    {"role": "system", "content": "历史: 直播间→battle→私信→约会"},
    {"role": "user", "content": user}
]
for i,m in enumerate(msgs):
    print(f"  [{i}] {m['role']}: {m['content'][:60]}")

d_out = call_llm(msgs, "Director")
print(f"\n【实际输出】: {d_out}\n")

# Predictor
print("=== Predictor ===")
print("【传入messages】")
msgs = [
    {"role": "system", "content": "你是Predictor。生成事件卡JSON"},
    {"role": "system", "content": f"六轴: {json.dumps(axes)}"},
    {"role": "system", "content": f"Director: {d_out[:80]}"},
    {"role": "user", "content": user}
]
for i,m in enumerate(msgs):
    print(f"  [{i}] {m['role']}: {m['content'][:60]}")

p_out = call_llm(msgs, "Predictor")
print(f"\n【实际输出】: {p_out}\n")

# Performer
print("=== Performer ===")
print("【传入messages】")
msgs = [
    {"role": "system", "content": "你是Performer。生成NPC对话JSON"},
    {"role": "system", "content": f"六轴: {json.dumps(axes)}"},
    {"role": "system", "content": "NPC: 沈予曦傲娇千金"},
    {"role": "user", "content": user}
]
for i,m in enumerate(msgs):
    print(f"  [{i}] {m['role']}: {m['content'][:60]}")

perf_out = call_llm(msgs, "Performer")
print(f"\n【实际输出】: {perf_out}\n")

# Observer
print("=== Observer ===")
print("【传入messages】")
msgs = [
    {"role": "system", "content": "你是Observer。评估剧情JSON"},
    {"role": "system", "content": "历史: 直播间→battle→私信→约会"},
    {"role": "user", "content": f"用户:{user} NPC:{perf_out[:50]}"}
]
for i,m in enumerate(msgs):
    print(f"  [{i}] {m['role']}: {m['content'][:60]}")

obs_out = call_llm(msgs, "Observer")
print(f"\n【实际输出】: {obs_out}\n")

print(f"\n{'='*60}")
print("完成")
print(f"{'='*60}")
