# -*- coding: utf-8 -*-
"""
10轮AB测试脚本 - 修复版
比较 有引擎(Director→Predictor→Performer) vs 无引擎(直接LLM对话)
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
LOG_BASE = os.path.join(WORKSPACE, "logic", "test_logs", "2026-02-26", "ab_test_001")
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

def call_direct_llm(user_input: str, history: list, npc_context: str) -> str:
    """无引擎：直接LLM对话（修复版：简化messages格式）"""
    # 构建历史
    history_str = ""
    for h in history[-3:]:
        history_str += f"用户: {h['user']}\nNPC: {h['npc']}\n"
    
    # 构建六轴状态
    axes_str = f"Intimacy={character['axes']['Intimacy']}, Risk={character['axes']['Risk']}, Info={character['axes']['Info']}, Action={character['axes']['Action']}, Rel={character['axes']['Rel']}, Growth={character['axes']['Growth']}"
    
    # 合并所有系统提示为单一消息
    system_content = f"""{npc_context}

当前六轴状态: {axes_str}
对话历史:
{history_str if history_str else "（暂无历史）"}"""

    # 简化版：单个system消息 + user消息
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

def run_without_engine(user_input: str, history: list, npc_context: str) -> dict:
    """无引擎：直接LLM"""
    npc_output = call_direct_llm(user_input, history, npc_context)
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
    print("10轮AB测试 - 修复版")
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
        
        # 跳过已完成的轮次（1-4）
        if round_num <= 4:
            print(f"\n[跳过] Round {round_num} 已完成")
            # 加载已有历史
            try:
                with_engine_log = os.path.join(LOG_BASE, f"run_{round_num:02d}_with_engine", "dialogue.json")
                with open(with_engine_log, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history_with_engine = data.get("history", [])
                without_engine_log = os.path.join(LOG_BASE, f"run_{round_num:02d}_without_engine", "dialogue.json")
                with open(without_engine_log, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history_without_engine = data.get("history", [])
            except:
                pass
            continue
        
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
            npc_with = f"[引擎错误: {e}]"
            history_with_engine.append({"user": user_input, "npc": npc_with})
        
        # ===== 无引擎 =====
        print(f"\n--- 无引擎测试 ---")
        try:
            output_without = run_without_engine(user_input, history_without_engine, npc_context)
            npc_without = output_without.get("npc", "")
            print(f"NPC回复: {npc_without[:100]}...")
            history_without_engine.append({"user": user_input, "npc": npc_without})
            save_round_log(round_num, False, user_input, output_without, history_without_engine)
        except Exception as e:
            print(f"无引擎测试失败: {e}")
            npc_without = f"[LLM错误: {e}]"
            history_without_engine.append({"user": user_input, "npc": npc_without})
        
        # 事件卡触发提示
        if round_num in EVENT_TRIGGER_ROUNDS:
            print(f"\n*** 事件卡触发轮次 (Round {round_num}) ***")
    
    print(f"\n{'='*60}")
    print("10轮AB测试完成！")
    print(f"日志位置: {LOG_BASE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
