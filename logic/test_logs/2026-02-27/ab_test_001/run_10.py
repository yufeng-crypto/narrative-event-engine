# -*- coding: utf-8 -*-
"""
完成第10轮测试
"""

import sys
import io
import json
import os
import time
from datetime import datetime

WORKSPACE = r"C:\Users\20731\.openclaw\workspace"
sys.path.insert(0, os.path.join(WORKSPACE, "logic", "engine"))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import engine_llm as eng

LOG_BASE = os.path.join(WORKSPACE, "logic", "test_logs", "2026-02-27", "ab_test_001")
CHARACTER_FILE = os.path.join(WORKSPACE, "logic", "test_logs", "2026-02-26", "character_palace.json")

with open(CHARACTER_FILE, 'r', encoding='utf-8') as f:
    character = json.load(f)

DIALOGUE_SCENARIOS = [
    {"type": "积极", "input": "姐姐一个人在这冷宫，可还好？"},
    {"type": "消极", "input": "随便你，我走了"},
    {"type": "冷淡", "input": "嗯"},
    {"type": "深入", "input": "你为什么会在冷宫？"},
    {"type": "好奇", "input": "姐姐以前在宫里是什么位份？"},
    {"type": "同情", "input": "这冷宫的生活一定很苦吧"},
    {"type": "试探", "input": "姐姐可曾后悔入宫？"},
    {"type": "关心", "input": "姐姐要注意身体才是"},
    {"type": "追问", "input": "那件事...就是姐姐家族蒙冤的事？"},
    {"type": "坦诚", "input": "实不相瞒，我是来帮姐姐的"},
]

def load_npc_context():
    npc_file = os.path.join(WORKSPACE, "logic", "roles", "npc_shenyuxi.md")
    try:
        with open(npc_file, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return f"你是沈氏，冷宫妃子"

def call_direct_llm(user_input: str, history: list, character_data: dict) -> str:
    history_str = ""
    for h in history[-5:]:
        history_str += f"用户: {h['user']}\nNPC: {h['npc']}\n"
    
    axes = character_data.get('axes', {})
    axes_str = f"Intimacy={axes.get('Intimacy', 2)}, Risk={axes.get('Risk', 3)}, Info={axes.get('Info', 4)}, Action={axes.get('Action', 5)}, Rel={axes.get('Rel', 1)}, Growth={axes.get('Growth', 7)}"
    role_content = character_data.get('content', '')
    
    system_content = f"""你是{character_data.get('name', '沈氏')}，角色设定如下：
{role_content}

当前六轴状态: {axes_str}

对话历史:
{history_str if history_str else "（暂无历史）"}

请根据以上角色设定和当前状态，以符合角色性格的方式回复用户。"""

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_input}
    ]
    
    for attempt in range(3):
        try:
            return eng.call_llm(messages)
        except Exception as e:
            print(f"  重试 {attempt+1}/3: {e}")
            time.sleep(5)
    return f"[LLM错误: {e}]"

def save_round_log(round_num, with_engine, test_input, output, history):
    prefix = "with_engine" if with_engine else "without_engine"
    round_dir = os.path.join(LOG_BASE, f"run_{round_num:02d}_{prefix}")
    os.makedirs(round_dir, exist_ok=True)
    
    with open(os.path.join(round_dir, "test_input.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "round": round_num,
            "type": prefix,
            "user_input": test_input,
            "timestamp": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    if with_engine:
        with open(os.path.join(round_dir, "director_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("director", "")}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(round_dir, "predictor_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("predictor", "")}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(round_dir, "performer_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("performer", "")}, f, ensure_ascii=False, indent=2)
    
    with open(os.path.join(round_dir, "dialogue.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "round": round_num,
            "user": test_input,
            "npc": output.get("npc", output.get("performer", "")),
            "history": history
        }, f, ensure_ascii=False, indent=2)
    
    print(f"  已保存 {round_dir}")

def load_history(round_num, prefix):
    dialogue_file = os.path.join(LOG_BASE, f"run_{round_num:02d}_{prefix}", "dialogue.json")
    try:
        with open(dialogue_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("history", [])
    except:
        return []

print("开始第10轮测试...")

npc_context = load_npc_context()
engine = eng.Engine()

# 加载1-9轮历史
history_with_engine = []
history_without_engine = []
for r in range(1, 10):
    he = load_history(r, "with_engine")
    if he:
        history_with_engine = he
    hoe = load_history(r, "without_engine")
    if hoe:
        history_without_engine = hoe

round_num = 10
scenario = DIALOGUE_SCENARIOS[9]
user_input = scenario["input"]

print(f"\n【Round {round_num}】{user_input}")

# 有引擎
print("\n--- 有引擎 ---")
try:
    output_with = engine.run_turn(user_input)
    npc_with = output_with.get("npc", "")
except Exception as e:
    print(f"错误: {e}")
    npc_with = f"[错误: {e}]"
    output_with = {"npc": npc_with}

print(f"NPC: {npc_with[:80]}...")
history_with_engine.append({"user": user_input, "npc": npc_with})
save_round_log(round_num, True, user_input, output_with, history_with_engine)

# 无引擎
print("\n--- 无引擎 ---")
npc_without = call_direct_llm(user_input, history_without_engine, character)
print(f"NPC: {npc_without[:80]}...")
history_without_engine.append({"user": user_input, "npc": npc_without})
save_round_log(round_num, False, user_input, {"npc": npc_without}, history_without_engine)

print("\n完成!")
