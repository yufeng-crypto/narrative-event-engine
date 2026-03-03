# -*- coding: utf-8 -*-
"""
10轮AB测试脚本 - 修复后重新运行
比较 有引擎(Director→Predictor→Performer) vs 无引擎(直接LLM对话)

关键修复：
1. 修复无引擎调用 - 确保传入完整角色设定
2. 确保每轮上下文正确传递
"""

import sys
import io
import json
import os
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

def load_npc_context():
    """加载NPC角色设定"""
    npc_file = os.path.join(WORKSPACE, "logic", "roles", "npc_shenyuxi.md")
    try:
        with open(npc_file, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return f"你是沈氏，冷宫妃子，请根据角色设定回复。"

def call_direct_llm(user_input: str, history: list, npc_context: str, character_data: dict) -> str:
    """
    无引擎：直接LLM对话
    修复版：确保传入完整角色设定
    """
    # 构建历史
    history_str = ""
    for h in history[-5:]:  # 保留最近5轮对话
        history_str += f"用户: {h['user']}\nNPC: {h['npc']}\n"
    
    # 构建六轴状态
    axes = character_data.get('axes', {})
    axes_str = f"Intimacy={axes.get('Intimacy', 2)}, Risk={axes.get('Risk', 3)}, Info={axes.get('Info', 4)}, Action={axes.get('Action', 5)}, Rel={axes.get('Rel', 1)}, Growth={axes.get('Growth', 7)}"
    
    # 完整角色设定
    role_content = character_data.get('content', '')
    
    # 合并所有系统提示为单一消息
    system_content = f"""你是{character_data.get('name', '沈氏')}，角色设定如下：
{role_content}

当前六轴状态: {axes_str}

对话历史:
{history_str if history_str else "（暂无历史）"}

请根据以上角色设定和当前状态，以符合角色性格的方式回复用户。"""

    # 构建消息列表
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_input}
    ]
    
    result = eng.call_llm(messages)
    return result

def run_with_engine(user_input: str, engine_instance) -> dict:
    """有引擎：Director→Predictor→Performer"""
    result = engine_instance.run_turn(user_input)
    return result

def run_without_engine(user_input: str, history: list, npc_context: str, character_data: dict) -> dict:
    """无引擎：直接LLM（修复版：传入完整角色设定）"""
    npc_output = call_direct_llm(user_input, history, npc_context, character_data)
    return {"npc": npc_output}

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

def main():
    print("=" * 60)
    print("10轮AB测试 - 修复后重新运行")
    print(f"角色: {character['name']} ({character['role_id']})")
    print(f"日志目录: {LOG_BASE}")
    print("=" * 60)
    
    npc_context = load_npc_context()
    
    # 初始化引擎
    engine = eng.Engine()
    
    # 历史记录
    history_with_engine = []
    history_without_engine = []
    
    # 10轮测试
    for i, scenario in enumerate(DIALOGUE_SCENARIOS):
        round_num = i + 1
        
        user_input = scenario["input"]
        
        print(f"\n{'='*50}")
        print(f"【Round {round_num}】场景: {scenario['type']}")
        print(f"用户输入: {user_input}")
        print(f"{'='*50}")
        
        # ===== 有引擎 =====
        print(f"\n--- 有引擎测试 ---")
        try:
            output_with = run_with_engine(user_input, engine)
            npc_with = output_with.get("npc", "")
            print(f"NPC回复: {npc_with[:100]}...")
            history_with_engine.append({"user": user_input, "npc": npc_with})
            save_round_log(round_num, True, user_input, output_with, history_with_engine)
        except Exception as e:
            print(f"有引擎测试失败: {e}")
            import traceback
            traceback.print_exc()
            npc_with = f"[引擎错误: {e}]"
            history_with_engine.append({"user": user_input, "npc": npc_with})
            save_round_log(round_num, True, user_input, {"npc": npc_with}, history_with_engine)
        
        # ===== 无引擎 =====
        print(f"\n--- 无引擎测试 ---")
        try:
            # 修复：传入完整角色设定 character
            output_without = run_without_engine(user_input, history_without_engine, npc_context, character)
            npc_without = output_without.get("npc", "")
            print(f"NPC回复: {npc_without[:100]}...")
            history_without_engine.append({"user": user_input, "npc": npc_without})
            save_round_log(round_num, False, user_input, output_without, history_without_engine)
        except Exception as e:
            print(f"无引擎测试失败: {e}")
            import traceback
            traceback.print_exc()
            npc_without = f"[LLM错误: {e}]"
            history_without_engine.append({"user": user_input, "npc": npc_without})
            save_round_log(round_num, False, user_input, {"npc": npc_without}, history_without_engine)
        
        # 事件卡触发提示
        if round_num in EVENT_TRIGGER_ROUNDS:
            print(f"\n*** 事件卡触发轮次 (Round {round_num}) ***")
    
    print(f"\n{'='*60}")
    print("10轮AB测试完成！")
    print(f"日志位置: {LOG_BASE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
