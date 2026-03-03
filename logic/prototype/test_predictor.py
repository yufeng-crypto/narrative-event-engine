# -*- coding: utf-8 -*-
"""测试 Predictor API 调用链"""

import json
import os
import sys
import glob
import requests
import time

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(__file__))

# 加载配置
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

CONFIG = load_config()

def load_npc_roles(roles_path):
    """读取 npc_*.md 文件作为角色设定"""
    pattern = os.path.join(roles_path, "npc_*.md")
    roles = {}

    default_axes = {
        "Intimacy": 50,
        "Risk": 20,
        "Info": 30,
        "Action": 40,
        "Rel": 60,
        "Growth": 25
    }

    for filepath in glob.glob(pattern):
        filename = os.path.basename(filepath)
        role_id = filename[4:-3]

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        role_name = role_id
        role_axes = default_axes.copy()

        roles[role_id] = {
            'name': role_name,
            'filepath': filepath,
            'content': content,
            'axes': role_axes
        }

    return roles

def call_predictor_api(user_message, role_content, axes_data, conversation_history):
    """调用 Predictor 生成事件卡"""
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            return {"error": "请在 config.json 中配置 API Key"}

        # 读取 predictor.md 提示词
        roles_path = CONFIG.get('roles_path', '')
        predictor_prompt_path = os.path.join(roles_path, "predictor.md")

        if os.path.exists(predictor_prompt_path):
            with open(predictor_prompt_path, 'r', encoding='utf-8') as f:
                predictor_prompt = f.read()
        else:
            predictor_prompt = """你是一个叙事预测引擎。根据对话和六轴状态，生成候选事件卡。

输出 JSON 格式：
{
  "events": [
    {"event_id": "EVT_001", "archetype": "母版类型", "title": "事件名称", "trigger": "触发条件", "plot_hook": "情节钩子"}
  ]
}"""

        # 构建对话摘要
        recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content'][:200]}"
            for m in recent_history
        ])

        axes_text = f"当前六轴状态: Intimacy={axes_data.get('Intimacy', 50)}, Risk={axes_data.get('Risk', 20)}, Info={axes_data.get('Info', 30)}, Action={axes_data.get('Action', 40)}, Rel={axes_data.get('Rel', 60)}, Growth={axes_data.get('Growth', 25)}"

        system_prompt = f"""{predictor_prompt}

角色设定：
{role_content[:1500]}

当前六轴状态：
{axes_text}

最近对话：
{conv_text}

用户最新输入：
{user_message}

请输出 JSON 格式的事件卡。"""

        url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": api_config.get('model', 'MiniMax-M2.5'),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请生成候选事件卡"}
            ]
        }

        print("正在调用 Predictor API...")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        result = response.json()

        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            return f"【API错误】{result}"

    except Exception as e:
        return f"【错误】{str(e)}"

def parse_predictor_events(predictor_output):
    """解析 Predictor 输出中的事件卡"""
    import re
    
    event_card = {
        "event_id": "",
        "archetype": "",
        "title": "",
        "trigger": "",
        "plot_hook": ""
    }
    
    try:
        # 尝试提取 JSON
        json_match = re.search(r'\{[\s\S]*\}', predictor_output)
        
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = predictor_output

        # 解析 JSON
        data = json.loads(json_str)

        # 提取事件列表
        events = data.get('events', [])
        if events and len(events) > 0:
            event = events[0]
            event_card = {
                "event_id": event.get('event_id', ''),
                "archetype": event.get('archetype', ''),
                "title": event.get('title', ''),
                "trigger": event.get('trigger', ''),
                "plot_hook": event.get('plot_hook', '')
            }
            return event_card

    except json.JSONDecodeError:
        pass

    # 备用：尝试从文本中提取字段
    try:
        event_id_match = re.search(r'event_id["\s:]+([A-Z0-9_]+)', predictor_output)
        archetype_match = re.search(r'archetype["\s:]+([^"\n]+)', predictor_output)
        title_match = re.search(r'title["\s:]+([^"\n]+)', predictor_output)
        trigger_match = re.search(r'trigger["\s:]+([^"\n]+)', predictor_output)
        plot_hook_match = re.search(r'plot_hook["\s:]+([^"\n]+)', predictor_output)

        if event_id_match or title_match:
            event_card = {
                "event_id": event_id_match.group(1) if event_id_match else "",
                "archetype": archetype_match.group(1).strip() if archetype_match else "",
                "title": title_match.group(1).strip() if title_match else "",
                "trigger": trigger_match.group(1).strip() if trigger_match else "",
                "plot_hook": plot_hook_match.group(1).strip() if plot_hook_match else ""
            }

    except Exception as e:
        print(f"解析事件卡失败: {e}")

    return event_card

# 主测试
if __name__ == "__main__":
    roles_path = CONFIG.get('roles_path', '')
    roles = load_npc_roles(roles_path)
    
    if not roles:
        print("未找到任何角色文件")
        sys.exit(1)
    
    # 选择第一个角色
    role_id = list(roles.keys())[0]
    role = roles[role_id]
    
    print(f"\n使用角色: {role['name']}")
    
    # 模拟对话历史
    conversation_history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你的吗？"},
        {"role": "user", "content": "我最近遇到了一些烦心事"},
        {"role": "assistant", "content": "怎么了？说说看"}
    ]
    
    # 当前六轴
    axes_data = {
        "Intimacy": 50,
        "Risk": 20,
        "Info": 30,
        "Action": 40,
        "Rel": 60,
        "Growth": 25
    }
    
    # 测试消息
    user_message = "我今天在街上看到了一个熟悉的身影，好像是我以前的朋友"
    
    print(f"\n用户消息: {user_message}")
    print("\n正在调用 Predictor API...")
    
    # 调用 Predictor API
    predictor_output = call_predictor_api(
        user_message,
        role['content'],
        axes_data,
        conversation_history
    )
    
    print("\n=== Predictor API 输出 ===")
    print(predictor_output)
    print("=" * 50)
    
    # 解析事件卡
    event_card = parse_predictor_events(predictor_output)
    
    print("\n=== 解析后的事件卡 ===")
    print(f"event_id: {event_card.get('event_id', '')}")
    print(f"archetype: {event_card.get('archetype', '')}")
    print(f"title: {event_card.get('title', '')}")
    print(f"trigger: {event_card.get('trigger', '')}")
    print(f"plot_hook: {event_card.get('plot_hook', '')}")
    
    # 验证格式
    has_event_id = bool(event_card.get('event_id'))
    has_archetype = bool(event_card.get('archetype'))
    has_title = bool(event_card.get('title'))
    has_trigger = bool(event_card.get('trigger'))
    has_plot_hook = bool(event_card.get('plot_hook'))
    
    print("\n=== 格式验证 ===")
    print(f"event_id: {'✓' if has_event_id else '✗'}")
    print(f"archetype: {'✓' if has_archetype else '✗'}")
    print(f"title: {'✓' if has_title else '✗'}")
    print(f"trigger: {'✓' if has_trigger else '✗'}")
    print(f"plot_hook: {'✓' if has_plot_hook else '✗'}")
    
    all_valid = has_event_id and has_archetype and has_title and has_trigger and has_plot_hook
    
    print(f"\n{'=' * 50}")
    if all_valid:
        print("总结: 通过 - 事件卡显示真实的 API 输出，格式正确")
    else:
        print("总结: 失败 - 事件卡格式不完整或有 placeholder")
