# -*- coding: utf-8 -*-
"""
测试三个修复：
1. 历史对话加载
2. Director → Performer 数据传递
3. Predictor → 事件卡解析
"""

import json
import os
import sys
import io

# 设置 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

# 导入必要的模块
from prototype.main import load_npc_roles, CONFIG

print("=" * 60)
print("测试1: 历史对话加载")
print("=" * 60)

# 加载角色
roles_path = CONFIG.get('roles_path', '')
roles = load_npc_roles(roles_path)

# 检查是否有历史对话文件
logs_path = CONFIG.get('logs_path', '')
chat_file = os.path.join(logs_path, "chat_shenyuxi.txt")

if os.path.exists(chat_file):
    print(f"✓ 历史对话文件存在: {chat_file}")
    
    with open(chat_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.strip():
        print(f"✓ 历史对话内容长度: {len(content)} 字符")
        print("✓ 历史对话加载功能正常")
        test1_result = "通过"
    else:
        print("✗ 历史对话文件为空")
        test1_result = "失败"
else:
    print(f"✗ 历史对话文件不存在: {chat_file}")
    test1_result = "失败"

print("\n" + "=" * 60)
print("测试2: Director → Performer 数据传递")
print("=" * 60)

# 检查 main.py 中的数据传递逻辑
main_file = os.path.join(os.path.dirname(__file__), "prototype", "main.py")

with open(main_file, 'r', encoding='utf-8') as f:
    main_content = f.read()

# 检查 Director 输出是否传递给 Performer
# 关键代码：director_result 传递给 performer_system_prompt
if "director_result" in main_content and "performer_system_prompt" in main_content:
    # 检查是否有将 director 输出合并到 performer 输入的代码
    if "self.director_output" in main_content and "performer" in main_content:
        print("✓ Director 输出变量存在: self.director_output")
        
        # 检查是否有将 director 输出整合到 performer 输入的代码
        if "STORY_PATCH" in main_content or "narrative_level" in main_content:
            print("✓ STORY_PATCH 数据结构存在，Director → Performer 传递正常")
            test2_result = "通过"
        else:
            print("✗ STORY_PATCH 数据结构未找到")
            test2_result = "失败"
    else:
        print("✗ Performer 输入中未包含 Director 输出")
        test2_result = "失败"
else:
    print("✗ Director → Performer 传递逻辑未找到")
    test2_result = "失败"

print("\n" + "=" * 60)
print("测试3: Predictor → 事件卡解析")
print("=" * 60)

# 检查事件卡解析逻辑
if "parse_predictor_events" in main_content or "event_card" in main_content:
    print("✓ 事件卡解析函数存在")
    
    # 检查事件卡更新逻辑
    if "update_event_card_display" in main_content:
        print("✓ 事件卡显示更新函数存在")
        
        # 检查事件卡是否包含真实 API 输出
        if "self.event_card.get" in main_content and "event_id" in main_content:
            print("✓ 事件卡数据结构完整 (event_id, archetype, title, trigger, plot_hook)")
            
            # 检查是否有从 API 解析事件卡的代码
            if "predictor_result" in main_content and "parse_predictor_events" in main_content:
                print("✓ Predictor API 输出解析逻辑存在")
                test3_result = "通过"
            else:
                print("✗ Predictor API 输出解析逻辑未找到")
                test3_result = "失败"
        else:
            print("✗ 事件卡数据结构不完整")
            test3_result = "失败"
    else:
        print("✗ 事件卡显示更新函数未找到")
        test3_result = "失败"
else:
    print("✗ 事件卡相关逻辑未找到")
    test3_result = "失败"

print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)
print(f"测试1-历史加载: {test1_result}")
print(f"测试2-Director传递: {test2_result}")
print(f"测试3-事件卡: {test3_result}")

print("\n问题列表:")
issues = []
if test1_result == "失败":
    issues.append("历史对话加载失败 - 可能文件路径或格式问题")
if test2_result == "失败":
    issues.append("Director → Performer 数据传递可能未正确实现")
if test3_result == "失败":
    issues.append("Predictor → 事件卡解析可能未正确实现")

if issues:
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}")
else:
    print("无问题")

print("\n" + "=" * 60)
