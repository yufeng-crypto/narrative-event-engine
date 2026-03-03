# -*- coding: utf-8 -*-
"""
测试 Performer 输出质量 - 根据 STORY_PATCH 生成输出
"""

import sys
import io
import json
import os

# 设置 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from engine_llm import (
    call_llm, 
    parse_with_schema, 
    get_role_prompt,
    PERFORMOR_SYSTEM_FALLBACK,
    merge_system_messages
)

# 测试输入 - 模拟 Director 输出的 STORY_PATCH
STORY_PATCH = {
    "narrative_level": "L1",
    "focus": "傲娇富家女的防线被温水关怀逐步瓦解",
    "logic_subtext": "明明在意的要死却嘴硬不肯承认，问忌口已经是她能做出的最大关怀表达",
    "thread_to_touch": "thread_meal_001 - 用餐场景的延续",
    "patch_status": "EVOLVE",
    "continuity_flag": True,
    "beat_plan": [
        {"beat": "reaction", "content": "听到'你点什么我都可以'时手指微微一顿，有些意外地抬眼"},
        {"beat": "evolution", "content": "嘴硬地哼了一声：'哼...那本小姐可就不客气了，把贵的都点一遍'"},
        {"beat": "hook", "content": "顿了顿，又装作不经意地问：'...你真的没有忌口？还是...就随便本小姐乱来？'"}
    ],
    "tension_tools": ["微碰触", "私人领地入侵", "推拉回复"],
    "hook": "...你真的没有忌口？还是...就随便本小姐乱来？",
    "hard_avoid": "禁止长篇大论解释、禁止突然暴露脆弱、禁止跳时间线"
}

# 模拟的用户输入和轴向
USER_INPUT = "你点什么我都可以"
CURRENT_AXES = {"intimacy": 4, "risk": 2, "info": 3, "action": 2, "rel": 3}

def test_performer():
    """测试 Performer 输出"""
    
    # 准备消息
    patch_str = json.dumps(STORY_PATCH, ensure_ascii=False)
    axes_str = json.dumps(CURRENT_AXES, ensure_ascii=False)
    
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
        {"role": "system", "content": f"六轴状态: {axes_str}"},
        {"role": "system", "content": f"用户输入: {USER_INPUT}"},
        {"role": "system", "content": f"STORY_PATCH: {patch_str}"},
        {"role": "system", "content": f"NPC角色设定:\n{npc_context}"},
        {"role": "user", "content": "请根据 STORY_PATCH 生成 NPC 对话和场景演绎。必须完整执行 beat_plan 的每一拍。"}
    ]
    performer_messages = merge_system_messages(performer_messages)
    
    print("="*60)
    print("Performer 测试开始")
    print("="*60)
    print(f"\n输入的 STORY_PATCH:\n{patch_str}\n")
    
    # 调用 LLM
    output = call_llm(performer_messages)
    
    print(f"\nPerformer 原始输出:\n{output}")
    print("\n" + "="*60)
    
    # 解析输出
    parsed = parse_with_schema(output, "performer")
    
    print("\n解析结果:")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    
    return output, parsed

def validate_output(output: str, parsed: dict):
    """验证输出是否符合要求"""
    
    print("\n" + "="*60)
    print("验证结果")
    print("="*60)
    
    results = {
        "beat_plan执行": {
            "reaction": "缺失",
            "evolution": "缺失", 
            "hook": "缺失"
        },
        "五感渲染": 0,
        "角色一致性": "符合"
    }
    
    output_lower = output.lower()
    
    # 1. beat_plan 执行完整性检查
    
    # 反应拍: "手指微微一顿", "有些意外", "抬眼"
    reaction_keywords = ["一顿", "意外", "抬眼", "手指", "微微"]
    has_reaction = any(kw in output for kw in reaction_keywords)
    results["beat_plan执行"]["reaction"] = "完整" if has_reaction else "缺失"
    
    # 演进拍: "哼", "本小姐", "不客气", "贵的都点一遍"
    evolution_keywords = ["哼", "本小姐", "不客气", "贵的", "点一遍"]
    has_evolution = any(kw in output for kw in evolution_keywords)
    results["beat_plan执行"]["evolution"] = "完整" if has_evolution else "缺失"
    
    # 钩子拍: 完整说出 hook 句
    hook_phrase = "忌口"
    has_hook = hook_phrase in output
    results["beat_plan执行"]["hook"] = "完整" if has_hook else "缺失"
    
    # 2. 五感渲染检查 - 至少 2 种感官
    sensory_keywords = {
        "视觉": ["看", "目光", "眼神", "视线", "眸", "眼", "瞥", "注视", "观察"],
        "听觉": ["听", "说", "声音", "语气", "语调", "话"],
        "触觉": ["碰", "触", "手指", "手", "肌肤", "温度"],
        "嗅觉": ["闻", "气味", "香味", "味道"],
        "味觉": ["尝", "味道", "口感", "吃"]
    }
    
    sensory_count = 0
    for sense, keywords in sensory_keywords.items():
        if any(kw in output for kw in keywords):
            sensory_count += 1
    
    results["五感渲染"] = sensory_count
    
    # 3. 角色一致性检查 - 傲娇富家女
    role_keywords = ["本小姐", "哼", "富人", "骄傲", "嘴硬"]
    has_role_consistency = any(kw in output for kw in role_keywords)
    results["角色一致性"] = "符合" if has_role_consistency else "不符合"
    
    # 打印验证结果
    print("\nbeat_plan执行:")
    print(f"  - 反应拍: {results['beat_plan执行']['reaction']}")
    print(f"  - 演进拍: {results['beat_plan执行']['evolution']}")
    print(f"  - 钩子拍: {results['beat_plan执行']['hook']}")
    print(f"\n五感渲染: {sensory_count} 种感官")
    print(f"角色一致性: {results['角色一致性']}")
    
    # 总结
    beat_complete = all(v == "完整" for v in results["beat_plan执行"].values())
    sensory_ok = sensory_count >= 2
    role_ok = results["角色一致性"] == "符合"
    
    if beat_complete and sensory_ok and role_ok:
        results["总结"] = "通过"
        print(f"\n总结: ✅ 通过")
    else:
        results["总结"] = "不通过"
        print(f"\n总结: ❌ 不通过")
        if not beat_complete:
            print("  - beat_plan 未完整执行")
        if not sensory_ok:
            print("  - 五感渲染不足")
        if not role_ok:
            print("  - 角色一致性不足")
    
    return results

if __name__ == "__main__":
    output, parsed = test_performer()
    results = validate_output(output, parsed)
    
    # 保存结果
    output_file = os.path.join(os.path.dirname(__file__), "performer_test_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "raw_output": output,
            "parsed": parsed,
            "validation": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {output_file}")
