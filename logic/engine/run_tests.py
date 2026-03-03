# -*- coding: utf-8 -*-
"""
测试脚本：运行 test_cases.json 中的测试用例
"""

import sys
import os
import json

# 添加路径
sys.path.insert(0, os.path.dirname(__file__))

from engine_llm import (
    call_llm, 
    parse_with_schema, 
    get_role_prompt,
    DIRECTOR_SYSTEM_FALLBACK,
    PERFORMOR_SYSTEM_FALLBACK,
    merge_system_messages
)

def run_director_test(test_case):
    """运行 Director 测试"""
    role = "Director"
    test_input = test_case["输入"]
    user_input = test_input["user_input"]
    axes = test_input["axes"]
    history = test_input.get("history", [])
    
    # 准备 axes 和 history 字符串
    axes_str = json.dumps(axes, ensure_ascii=False)
    history_str = "\n".join(history) if history else "（暂无历史）"
    
    # 构建消息
    director_messages = [
        {"role": "system", "content": get_role_prompt("director") or DIRECTOR_SYSTEM_FALLBACK},
        {"role": "system", "content": f"六轴状态:\n{axes_str}"},
        {"role": "system", "content": f"对话历史:\n{history_str}"},
        {"role": "user", "content": f"用户输入: {user_input}\n请输出JSON决策"}
    ]
    director_messages = merge_system_messages(director_messages)
    
    # 调用 LLM
    output = call_llm(director_messages)
    
    # 解析输出
    parsed = parse_with_schema(output, "director")
    
    # 检查格式
    is_json_valid = not parsed.get("parse_error", True)
    
    # 检查字段完整性 (Director 需要 beat, axis_changes)
    data = parsed.get("data", {})
    has_beat = "beat" in data
    has_axis_changes = "axis_changes" in data
    is_fields_complete = has_beat and has_axis_changes
    
    return {
        "实际输出": output[:500] if len(output) > 500 else output,
        "解析后数据": data,
        "格式合规": is_json_valid,
        "字段完整": is_fields_complete
    }

def run_performer_test(test_case):
    """运行 Performer 测试"""
    role = "Performer"
    test_input = test_case["输入"]
    user_input = test_input["user_input"]
    axes = test_input["axes"]
    history = test_input.get("history", [])
    
    # 准备字符串
    axes_str = json.dumps(axes, ensure_ascii=False)
    history_str = "\n".join(history) if history else "（暂无历史）"
    
    # 获取 NPC 上下文
    npc_context_file = os.path.join(os.path.dirname(__file__), "..", "roles", "npc_shenyuxi.md")
    try:
        with open(npc_context_file, 'r', encoding='utf-8') as f:
            npc_context = f.read()
    except:
        npc_context = "你是沈予曦，请根据角色设定回复。"
    
    # 构建消息
    performer_messages = [
        {"role": "system", "content": get_role_prompt("performer") or PERFORMOR_SYSTEM_FALLBACK},
        {"role": "system", "content": f"六轴: {axes_str}"},
        {"role": "system", "content": f"历史: {history_str}"},
        {"role": "system", "content": f"NPC设定: {npc_context}"},
        {"role": "user", "content": f"用户: {user_input}\n请生成NPC对话"}
    ]
    performer_messages = merge_system_messages(performer_messages)
    
    # 调用 LLM
    output = call_llm(performer_messages)
    
    # 解析输出
    parsed = parse_with_schema(output, "performer")
    
    # 检查格式
    is_json_valid = not parsed.get("parse_error", True)
    
    # 检查字段完整性 (Performer 需要 scene, dialogue)
    data = parsed.get("data", {})
    has_scene = "scene" in data
    has_dialogue = "dialogue" in data
    is_fields_complete = has_scene and has_dialogue
    
    return {
        "实际输出": output[:500] if len(output) > 500 else output,
        "解析后数据": data,
        "格式合规": is_json_valid,
        "字段完整": is_fields_complete
    }

def main():
    # 加载测试用例
    test_file = os.path.join(os.path.dirname(__file__), "..", "roles", "test_cases.json")
    with open(test_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    test_cases = data["test_cases"]
    
    results = []
    total = len(test_cases)
    valid_format_count = 0
    valid_fields_count = 0
    
    print(f"\n{'='*60}")
    print(f"开始测试: 共 {total} 个用例")
    print(f"{'='*60}\n")
    
    for i, tc in enumerate(test_cases):
        role = tc["role"]
        scene_name = tc["场景名"]
        
        print(f"[{i+1}/{total}] 测试 {scene_name} ({role})...")
        
        try:
            if role == "Director":
                result = run_director_test(tc)
            else:
                result = run_performer_test(tc)
            
            # 记录结果
            test_result = {
                "场景名": scene_name,
                "role": role,
                "实际输出": result["实际输出"],
                "格式合规": result["格式合规"],
                "字段完整": result["字段完整"]
            }
            results.append(test_result)
            
            if result["格式合规"]:
                valid_format_count += 1
            if result["字段完整"]:
                valid_fields_count += 1
            
            print(f"  OK 格式合规: {result['格式合规']}, 字段完整: {result['字段完整']}")
            
        except Exception as e:
            print(f"  ERROR 错误: {e}")
            results.append({
                "场景名": scene_name,
                "role": role,
                "实际输出": f"[错误: {e}]",
                "格式合规": False,
                "字段完整": False
            })
    
    # 输出汇总
    print(f"\n{'='*60}")
    print(f"测试完成!")
    print(f"总用例数: {total}")
    print(f"格式合规率: {valid_format_count}/{total} = {valid_format_count/total*100:.1f}%")
    print(f"字段完整率: {valid_fields_count}/{total} = {valid_fields_count/total*100:.1f}%")
    print(f"{'='*60}")
    
    # 输出 JSON 格式结果
    output = {
        "test_results": results,
        "summary": {
            "total": total,
            "格式合规率": f"{valid_format_count/total*100:.1f}%",
            "字段完整率": f"{valid_fields_count/total*100:.1f}%"
        }
    }
    
    # 保存结果
    output_file = os.path.join(os.path.dirname(__file__), "test_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
    
    return output

if __name__ == "__main__":
    main()
