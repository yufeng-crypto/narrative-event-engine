# -*- coding: utf-8 -*-
"""
爱巴基斯坦叙事引擎 - 详细调试版
"""
import sys
import io
import json
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==================== 配置 ====================
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"api_key": "", "api_url": "", "model": "MiniMax-M2.5"}

CONFIG = load_config()
API_KEY = CONFIG.get("api_key", "")
API_URL = CONFIG.get("api_url", "https://api.minimaxi.com/v1/text/chatcompletion_v2")
MODEL = CONFIG.get("model", "MiniMax-M2.5")

# ==================== LLM 调用 ====================
def call_llm(messages: list, max_tokens: int = 1024) -> str:
    try:
        import urllib.request
        
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": CONFIG.get("temperature", 0.7),
            "max_completion_tokens": max_tokens
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(API_URL, data=data, method='POST')
        req.add_header("Authorization", f"Bearer {API_KEY}")
        req.add_header("Content-Type", "application/json")
        
        response = urllib.request.urlopen(req, timeout=30)
        result = json.loads(response.read().decode('utf-8'))
        
        if "reply" in result and result["reply"]:
            return result["reply"]
        
        choices = result.get("choices", [])
        if choices and len(choices) > 0:
            return choices[0].get("message", {}).get("content", "")
        
        return f"[API返回空: {result}]"
        
    except Exception as e:
        return f"[LLM调用失败: {e}]"

# ==================== Prompt模板 ====================
DIRECTOR_PROMPT = "你是Director。根据六轴和对话判定节拍，输出JSON：{\"beat\": \"STALL|HOLD|EVOLVE|PIVOT\", \"axis_changes\": {}, \"reasoning\": \"\"}"

PREDICTOR_PROMPT = "你是Predictor。根据决策生成事件卡，输出JSON：{\"events\": [{\"event_id\": \"\", \"archetype\": \"\", \"title\": \"\", \"trigger\": \"\", \"plot_hook\": \"\"}]}"

PERFORMER_PROXT = "你是Performer。生成NPC对话，输出JSON：{\"scene\": \"\", \"dialogue\": {\"reaction\": \"\", \"evolution\": \"\", \"hook\": \"\"}, \"emotion\": \"\"}"

OBSERVER_PROMPT = "你是Observer。评估剧情，输出JSON：{\"scores\": {\"emotion_curve\": 1, \"suspense\": 1, \"memory\": 1, \"immersion\": 1}, \"summary\": \"\"}"

# ==================== 状态 ====================
class State:
    def __init__(self):
        self.axes = {"Intimacy": 10, "Risk": 5, "Info": 9, "Action": 8, "Rel": 10, "Growth": 9}
        self.history = []
        self.round = 0
        self.npc = "沈予曦"

state = State()

# ==================== 显示函数 ====================
def show_messages(msgs: list, title: str = "messages"):
    print(f"\n=== {title} ===")
    for i, m in enumerate(msgs):
        role = m.get("role", "?")
        content = m.get("content", "")
        # 只显示前200字符
        display = content[:200] + "..." if len(content) > 200 else content
        print(f"[{i}] role={role}")
        print(f"    content: {display}")
    print("="*30)

# ==================== 模拟 Director ====================
def run_director(user_input: str):
    print(f"\n{'#'*60}")
    print(f"【Director】处理用户输入: {user_input}")
    print(f"#"*60)
    
    messages = [
        {"role": "system", "content": DIRECTOR_PROMPT},
        {"role": "system", "content": f"当前六轴: {json.dumps(state.axes, ensure_ascii=False)}"},
        {"role": "system", "content": f"对话历史: {state.history[-3:] if state.history else '无'}"},
        {"role": "system", "content": f"NPC角色: 沈予曦，24岁傲娇千金主播"},
        {"role": "user", "content": f"用户说: {user_input}\n请输出JSON决策"}
    ]
    
    show_messages(messages, "Director收到的messages")
    
    output = call_llm(messages)
    print(f"\n>>> Director输出: {output[:300]}...")
    
    return output

# ==================== 模拟 Predictor ====================
def run_predictor(user_input: str, director_output: str):
    print(f"\n{'#'*60}")
    print(f"【Predictor】处理")
    print(f"#"*60)
    
    messages = [
        {"role": "system", "content": PREDICTOR_PROMPT},
        {"role": "system", "content": f"六轴: {json.dumps(state.axes)}"},
        {"role": "system", "content": f"Director决策: {director_output[:200]}"},
        {"role": "user", "content": f"用户: {user_input}\n请生成事件"}
    ]
    
    show_messages(messages, "Predictor收到的messages")
    
    output = call_llm(messages)
    print(f"\n>>> Predictor输出: {output[:300]}...")
    
    return output

# ==================== 模拟 Performer ====================
def run_performer(user_input: str, director_output: str, predictor_output: str):
    print(f"\n{'#'*60}")
    print(f"【Performer】处理")
    print(f"#"*60)
    
    messages = [
        {"role": "system", "content": PERFORMER_PROXT},
        {"role": "system", "content": f"六轴: {json.dumps(state.axes)}"},
        {"role": "system", "content": f"Director决策: {director_output[:200]}"},
        {"role": "system", "content": f"事件: {predictor_output[:200]}"},
        {"role": "system", "content": "NPC: 沈予曦，24岁，傲娇千金主播，性格傲慢毒舌但内心孤独"},
        {"role": "user", "content": f"用户: {user_input}\n请生成对话"}
    ]
    
    show_messages(messages, "Performer收到的messages")
    
    output = call_llm(messages)
    print(f"\n>>> Performer输出: {output[:300]}...")
    
    return output

# ==================== 模拟 Observer ====================
def run_observer(user_input: str, performer_output: str):
    print(f"\n{'#'*60}")
    print(f"【Observer】处理")
    print(f"#"*60)
    
    messages = [
        {"role": "system", "content": OBSERVER_PROMPT},
        {"role": "system", "content": f"历史: {state.history[-3:] if state.history else '无'}"},
        {"role": "user", "content": f"用户: {user_input}\nNPC: {performer_output[:200]}\n请评估"}
    ]
    
    show_messages(messages, "Observer收到的messages")
    
    output = call_llm(messages)
    print(f"\n>>> Observer输出: {output[:300]}...")
    
    return output

# ==================== 主程序 ====================
if __name__ == "__main__":
    user_input = "我到了约定的餐厅，拨通了沈予曦的电话"
    
    print(f"\n{'='*60}")
    print(f"开始模拟 - 用户输入: {user_input}")
    print(f"当前六轴: {state.axes}")
    print(f"{'='*60}")
    
    d_out = run_director(user_input)
    p_out = run_predictor(user_input, d_out)
    perf_out = run_performer(user_input, d_out, p_out)
    obs_out = run_observer(user_input, perf_out)
    
    print(f"\n{'='*60}")
    print("模拟完成")
    print(f"{'='*60}")
