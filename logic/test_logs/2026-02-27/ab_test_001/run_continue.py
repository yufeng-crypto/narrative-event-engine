# -*- coding: utf-8 -*-
"""
10轮AB测试脚本 - 继续运行剩余轮次
从第4轮开始运行，增加重试机制
"""

import sys
import io
import json
import os
import time
from datetime import datetime

# 设置工作目录
WORKSPACE = r"C:\Users\20731\.openclaw\workspace"
sys.path.insert(0, os.path.join(WORKSPACE, "logic", "engine"))

# 修复编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import engine_llm as eng

# 测试配置
LOG_BASE = os.path.join(WORKSPACE, "logic", "test_logs", "2026-02-27", "ab_test_001")
CHARACTER_FILE = os.path.join(WORKSPACE, "logic", "test_logs", "2026-02-26", "character_palace.json")

# 加载角色配置
with open(CHARACTER_FILE, 'r', encoding='utf-8') as f:
    character = json.load(f)

# 10轮对话场景
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

# 事件卡触发轮次
EVENT_TRIGGER_ROUNDS = [4, 9]

MAX_RETRIES = 3
RETRY_DELAY = 5

def load_npc_context():
    """加载NPC角色设定"""
    npc_file = os.path.join(WORKSPACE, "logic", "roles", "npc_shenyuxi.md")
    try:
        with open(npc_file, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return f"你是沈氏，冷宫妃子，请根据角色设定回复。"

def call_direct_llm_with_retry(user_input: str, history: list, npc_context: str, character_data: dict) -> str:
    """无引擎：直接LLM对话 - 带重试"""
    for attempt in range(MAX_RETRIES):
        try:
            # 构建历史
            history_str = ""
            for h in history[-5:]:
                history_str += f"用户: {h['user']}\nNPC: {h['npc']}\n"
            
            # 构建六轴状态
            axes = character_data.get('axes', {})
            axes_str = f"Intimacy={axes.get('Intimacy', 2)}, Risk={axes.get('Risk', 3)}, Info={axes.get('Info', 4)}, Action={axes.get('Action', 5)}, Rel={axes.get('Rel', 1)}, Growth={axes.get('Growth', 7)}"
            
            # 完整角色设定
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
            
            result = eng.call_llm(messages)
            return result
            
        except Exception as e:
            print(f"  [重试 {attempt+1}/{MAX_RETRIES}] 错误: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return f"[LLM调用失败: {e}]"

def run_with_engine_with_retry(user_input: str, engine_instance) -> dict:
    """有引擎：带重试"""
    for attempt in range(MAX_RETRIES):
        try:
            result = engine_instance.run_turn(user_input)
            return result
        except Exception as e:
            print(f"  [重试 {attempt+1}/{MAX_RETRIES}] 错误: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return {"npc": f"[引擎错误: {e}]", "director": "", "predictor": "", "performer": ""}

def save_round_log(round_num: int, with_engine: bool, test_input: str, output: dict, history: list):
    """保存单轮测试日志"""
    prefix = "with_engine" if with_engine else "without_engine"
    round_dir = os.path.join(LOG_BASE, f"run_{round_num:02d}_{prefix}")
    os.makedirs(round_dir, exist_ok=True)
    
    # 保存输入
    with open(os.path.join(round_dir, "test_input.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "round": round_num,
            "type": "with_engine" if with_engine else "without_engine",
            "user_input": test_input,
            "timestamp": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    # 保存各层输出
    if with_engine:
        with open(os.path.join(round_dir, "director_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("director", "")}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(round_dir, "predictor_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("predictor", "")}, f, ensure_ascii=False, indent=2)
        with open(os.path.join(round_dir, "performer_output.json"), 'w', encoding='utf-8') as f:
            json.dump({"raw": output.get("performer", "")}, f, ensure_ascii=False, indent=2)
    
    # 保存对话内容
    with open(os.path.join(round_dir, "dialogue.json"), 'w', encoding='utf-8') as f:
        json.dump({
            "round": round_num,
            "user": test_input,
            "npc": output.get("npc", output.get("performer", "")),
            "history": history
        }, f, ensure_ascii=False, indent=2)
    
    print(f"  [已保存] {round_dir}")

def load_history(round_num: int, prefix: str) -> list:
    """加载已有的历史记录"""
    dialogue_file = os.path.join(LOG_BASE, f"run_{round_num:02d}_{prefix}", "dialogue.json")
    try:
        with open(dialogue_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("history", [])
    except:
        return []

def main():
    print("=" * 60)
    print("10轮AB测试 - 继续运行（第4-10轮）")
    print(f"角色: {character['name']} ({character['role_id']})")
    print(f"日志目录: {LOG_BASE}")
    print("=" * 60)
    
    npc_context = load_npc_context()
    
    # 初始化引擎
    engine = eng.Engine()
    
    # 加载已有历史（从第1轮开始）
    history_with_engine = []
    history_without_engine = []
    
    # 加载1-3轮的历史
    for r in range(1, 4):
        he = load_history(r, "with_engine")
        if he:
            history_with_engine = he
        hoe = load_history(r, "without_engine")
        if hoe:
            history_without_engine = hoe
    
    print(f"\n已加载历史: 有引擎 {len(history_with_engine)} 轮, 无引擎 {len(history_without_engine)} 轮")
    
    # 从第4轮开始运行
    start_round = 4
    
    for i in range(start_round - 1, len(DIALOGUE_SCENARIOS)):
        scenario = DIALOGUE_SCENARIOS[i]
        round_num = i + 1
        
        user_input = scenario["input"]
        
        print(f"\n{'='*50}")
        print(f"【Round {round_num}】场景: {scenario['type']}")
        print(f"用户输入: {user_input}")
        print(f"{'='*50}")
        
        # ===== 有引擎 =====
        print(f"\n--- 有引擎测试 ---")
        output_with = run_with_engine_with_retry(user_input, engine)
        npc_with = output_with.get("npc", "")
        print(f"NPC回复: {npc_with[:100]}...")
        history_with_engine.append({"user": user_input, "npc": npc_with})
        save_round_log(round_num, True, user_input, output_with, history_with_engine)
        
        # ===== 无引擎 =====
        print(f"\n--- 无引擎测试 ---")
        output_without_npc = call_direct_llm_with_retry(user_input, history_without_engine, npc_context, character)
        print(f"NPC回复: {output_without_npc[:100]}...")
        history_without_engine.append({"user": user_input, "npc": output_without_npc})
        save_round_log(round_num, False, user_input, {"npc": output_without_npc}, history_without_engine)
        
        # 事件卡触发提示
        if round_num in EVENT_TRIGGER_ROUNDS:
            print(f"\n*** 事件卡触发轮次 (Round {round_num}) ***")
        
        # 短暂休息
        time.sleep(2)
    
    print(f"\n{'='*60}")
    print("10轮AB测试完成！")
    print(f"日志位置: {LOG_BASE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
