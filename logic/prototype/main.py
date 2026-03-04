# -*- coding: utf-8 -*-
"""
NPC Chat Prototype - 本地 Windows GUI 程序
功能：角色选择、对话、记录保存、Observer 分析
"""

import json
import os
import glob
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
import requests
import threading
import time
import traceback

# ============= 日志系统 =============
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs", "debug")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

def log(level, tag, message, extra=""):
    """统一的日志记录函数"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    log_line = f"[{timestamp}] [{level}] [{tag}] {message}"
    if extra:
        log_line += f"\n    Extra: {extra}"
    
    # 打印到控制台
    print(log_line)
    
    # 写入文件
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line + "\n")
    except:
        pass
    
    return log_line

def log_info(tag, message, extra=""):
    return log("INFO", tag, message, extra)

def log_error(tag, message, extra=""):
    return log("ERROR", tag, message, extra)

def log_debug(tag, message, extra=""):
    return log("DEBUG", tag, message, extra)

def log_api_request(tag, url, headers, data):
    """记录API请求详细信息"""
    # 隐藏敏感信息
    safe_headers = headers.copy()
    if "Authorization" in safe_headers:
        safe_headers["Authorization"] = "Bearer ***"
    if "api_key" in data.get("model", ""):
        data = data.copy()
        data["model"] = "***"
    
    extra = f"URL: {url}\nHeaders: {json.dumps(safe_headers, ensure_ascii=False)}\nData: {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}"
    return log_debug(tag, "API请求", extra)

def log_api_response(tag, result, content_preview=""):
    """记录API响应"""
    result_str = str(result)[:500]
    extra = f"Result: {result_str}"
    if content_preview:
        extra += f"\nContent Preview: {content_preview[:500]}"
    return log_debug(tag, "API响应", extra)

# 启动时记录
log_info("MAIN", f"程序启动，日志文件: {LOG_FILE}")

# 导入引擎对接层
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
try:
    from engine_llm import Engine, create_engine, start_engine, chat, get_state, save_state
    ENGINE_AVAILABLE = True
    log_info("ENGINE", "引擎模块加载成功")
except Exception as e:
    log_error("ENGINE", f"引擎加载失败: {e}", traceback.format_exc())
    ENGINE_AVAILABLE = False

# ============= 配置 =============
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

CONFIG = load_config()

# ============= 角色加载 =============
def load_npc_roles(roles_path):
    """读取 npc_*.md 文件作为角色设定"""
    pattern = os.path.join(roles_path, "npc_*.md")
    roles = {}

    # 默认六轴值
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
        # 提取角色名: npc_xxx.md -> xxx
        role_id = filename[4:-3]  # 去掉 "npc_" 和 ".md"

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取角色名（从 # NPC Role: xxx）
        role_name = role_id
        role_axes = default_axes.copy()  # 默认六轴值

        # 解析六轴初始值 - 支持多种格式
        in_axes_section = False
        for line in content.split('\n'):
            if line.startswith('# NPC Role:'):
                role_name = line.replace('# NPC Role:', '').strip()

            # 检测轴向部分开始 (支持 "轴向:", "初始状态:", "Axes:" 等)
            line_stripped = line.strip()
            if '轴向' in line_stripped or '初始状态' in line_stripped or line_stripped.startswith('### Axes'):
                in_axes_section = True
                continue

            # 在轴向部分中，解析 Intimacy, Risk, Info, Action, Rel, Growth
            if in_axes_section:
                # 遇到空行或新的章节标题则退出
                if line_stripped == '' or line_stripped.startswith('##'):
                    in_axes_section = False
                    continue

                # 解析形如 "  - Intimacy = 10 🔒" 或 "  - Intimacy: 10" 或 "- Intimacy: 2" 的格式
                for axis_name in ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]:
                    if axis_name in line:
                        try:
                            import re
                            match = re.search(r'[=:]\s*(\d+)', line)
                            if match:
                                role_axes[axis_name] = int(match.group(1))
                        except:
                            pass

        roles[role_id] = {
            'name': role_name,
            'filepath': filepath,
            'content': content,
            'axes': role_axes  # 每个角色独立的六轴初始值
        }

    return roles

# ============= API 调用 =============
def call_minimax_api(messages, role_content, user_message):
    """调用 MiniMax API 生成回复 (Performer)"""
    log_info("PERFORMER", "开始调用LLM", f"messages数量: {len(messages)}, user_message: {user_message[:50]}...")
    
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            log_error("PERFORMER", "API Key未配置")
            return "【错误】请在 config.json 中配置 API Key"

        # 构建系统提示词（角色设定）
        system_prompt = f"""你是一个名为的角色。请严格按照以下角色设定进行对话：

{role_content}

请用角色的口吻和性格回复用户。"""

        # API 请求
        url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": api_config.get('model', 'MiniMax-M2.5'),
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
                {"role": "user", "content": user_message}
            ]
        }

        log_api_request("PERFORMER", url, headers, data)
        
        log_debug("PERFORMER", "发送请求到API", f"timeout: 120s")
        response = requests.post(url, headers=headers, json=data, timeout=120)
        
        log_debug("PERFORMER", "收到响应", f"status_code: {response.status_code}, headers: {dict(response.headers)}")
        result = response.json()
        
        log_api_response("PERFORMER", result, result.get('choices', [{}])[0].get('message', {}).get('content', '')[:200] if result.get('choices') else "")

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            log_info("PERFORMER", "LLM调用成功", f"回复长度: {len(content)}")
            return content
        else:
            log_error("PERFORMER", "API返回格式异常", json.dumps(result, ensure_ascii=False))
            return f"【API错误】{result}"

    except requests.exceptions.Timeout:
        log_error("PERFORMER", "API请求超时", "timeout=120s")
        return "【错误】API请求超时"
    except requests.exceptions.ConnectionError as e:
        log_error("PERFORMER", "API连接失败", str(e))
        return f"【错误】连接失败: {str(e)}"
    except Exception as e:
        log_error("PERFORMER", "LLM调用异常", f"{str(e)}\n{traceback.format_exc()}")
        return f"【错误】{str(e)}"

def call_director_api(conversation_history, role_content, axes_data, event_card=None):
    """调用 Director 生成 STORY_PATCH (第一个版本，兼容旧代码)"""
    log_info("DIRECTOR", "开始调用Director", f"conversation_history长度: {len(conversation_history)}, event_card: {event_card.get('event_id') if event_card else 'None'}")
    
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            log_error("DIRECTOR", "API Key未配置")
            return {"error": "请在 config.json 中配置 API Key"}

        # 读取 director.md 提示词
        roles_path = CONFIG.get('roles_path', '')
        director_prompt_path = os.path.join(roles_path, "director.md")

        if os.path.exists(director_prompt_path):
            with open(director_prompt_path, 'r', encoding='utf-8') as f:
                director_prompt = f.read()
            log_debug("DIRECTOR", f"加载提示词文件: {director_prompt_path}")
        else:
            # 如果没有 director.md，使用内置提示词
            director_prompt = """你是一个 Narrative Director（叙事指挥中枢）。

你需要根据对话历史和角色设定，输出 STORY_PATCH 来驱动表演模型。

输出格式（严格）：
===STORY_PATCH_BEGIN===
[STORY_PATCH]
- narrative_level: L0|L1|L2
- focus: （本轮重点体验，用自然语言）
- logic_subtext: （NPC 此时的心理潜台词）
- thread_to_touch: （若有，用 thread_id + 一句话）
- patch_status: 明确标注 [STALL / HOLD / EVOLVE / PIVOT]
- continuity_flag: 当状态为 HOLD 或 EVOLVE 时，此项为 true
- beat_plan: 1.反应拍、2.演进拍、3.钩子拍
- tension_tools: 工具A、工具B
- hook: （一个问题 或 二选一）
- hard_avoid: 禁止项列表
===STORY_PATCH_END===

===STATE_UPDATE_JSON===
{
  "driving_signals": { "initiative": x, "intent": "...", "affect": "...", "stall": x },
  "axes_next": { "Intimacy": x, "Risk": x, "Info": x, "Action": x, "Rel": x, "Growth": x },
  "momentum_next": { ... },
  "open_threads_next": [ ... ],
  "meta": { "priority_hit": "P0-P4", "level": "L0-L2" }
}
===STATE_UPDATE_END==="""
            log_debug("DIRECTOR", "使用内置提示词")

        # 构建对话摘要
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content'][:200]}"
            for m in conversation_history[-5:]
        ])

        axes_text = f"当前六轴状态: Intimacy={axes_data.get('Intimacy', 50)}, Risk={axes_data.get('Risk', 20)}, Info={axes_data.get('Info', 30)}, Action={axes_data.get('Action', 40)}, Rel={axes_data.get('Rel', 60)}, Growth={axes_data.get('Growth', 25)}"

        # 事件卡信息（包含 plot_hook）
        event_text = ""
        if event_card:
            event_id = event_card.get('event_id', '')
            archetype = event_card.get('archetype', '')
            title = event_card.get('title', '')
            plot_hook = event_card.get('plot_hook', '')
            trigger = event_card.get('trigger', '')
            
            if title or plot_hook:
                event_text = f"""当前事件卡:
- event_id: {event_id}
- archetype: {archetype}
- title: {title}
- trigger: {trigger}
- plot_hook: {plot_hook}

【重要】请将事件卡的 plot_hook 填入 STORY_PATCH 的 focus 字段，作为本轮对话的重点。"""
                log_debug("DIRECTOR", f"事件卡信息: {title}, plot_hook: {plot_hook[:50]}...")

        system_prompt = f"""{director_prompt}

角色设定：
{role_content[:1500]}

当前六轴状态：
{axes_text}

{event_text}

对话历史（最近5轮）：
{conv_text}

请根据以上信息，输出 STORY_PATCH。"""

        url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": api_config.get('model', 'MiniMax-M2.5'),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请生成 STORY_PATCH"}
            ]
        }

        log_api_request("DIRECTOR", url, headers, data)

        for attempt in range(3):
            try:
                log_debug("DIRECTOR", f"API请求尝试 {attempt + 1}/3", f"timeout: 60s")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                log_debug("DIRECTOR", f"收到响应", f"status_code: {response.status_code}")
                break
            except Exception as e:
                log_error("DIRECTOR", f"API请求失败 {attempt + 1}/3", str(e))
                if attempt == 2:
                    raise e
                time.sleep(2)

        result = response.json()
        log_api_response("DIRECTOR", result, result.get('choices', [{}])[0].get('message', {}).get('content', '')[:200] if result.get('choices') else "")

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            log_info("DIRECTOR", "Director调用成功", f"回复长度: {len(content)}")
            return content
        else:
            log_error("DIRECTOR", "API返回格式异常", json.dumps(result, ensure_ascii=False))
            return f"【API错误】{result}"

    except requests.exceptions.Timeout:
        log_error("DIRECTOR", "API请求超时", "timeout=60s")
        return f"【错误】API请求超时"
    except requests.exceptions.ConnectionError as e:
        log_error("DIRECTOR", "API连接失败", str(e))
        return f"【错误】连接失败: {str(e)}"
    except Exception as e:
        log_error("DIRECTOR", "Director调用异常", f"{str(e)}\n{traceback.format_exc()}")
        return f"【错误】{str(e)}"

def call_predictor_api(user_message, role_content, axes_data, conversation_history):
    """调用 Predictor 生成事件卡"""
    log_info("PREDICTOR", "开始调用Predictor", f"user_message: {user_message[:50]}...")
    
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            log_error("PREDICTOR", "API Key未配置")
            return {"error": "请在 config.json 中配置 API Key"}

        # 读取 predictor.md 提示词
        roles_path = CONFIG.get('roles_path', '')
        predictor_prompt_path = os.path.join(roles_path, "predictor.md")

        if os.path.exists(predictor_prompt_path):
            with open(predictor_prompt_path, 'r', encoding='utf-8') as f:
                predictor_prompt = f.read()
            log_debug("PREDICTOR", f"加载提示词文件: {predictor_prompt_path}")
        else:
            # 如果没有 predictor.md，使用内置提示词
            predictor_prompt = """你是一个叙事预测引擎。根据对话和六轴状态，生成候选事件卡。

输出 JSON 格式：
{
  "events": [
    {"event_id": "EVT_001", "archetype": "母版类型", "title": "事件名称", "trigger": "触发条件", "plot_hook": "情节钩子"}
  ]
}"""
            log_debug("PREDICTOR", "使用内置提示词")

        # 构建对话摘要
        recent_history = conversation_history[-5:]  # 最近5轮
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

        log_api_request("PREDICTOR", url, headers, data)

        for attempt in range(3):
            try:
                log_debug("PREDICTOR", f"API请求尝试 {attempt + 1}/3", f"timeout: 60s")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                log_debug("PREDICTOR", f"收到响应", f"status_code: {response.status_code}")
                break
            except Exception as e:
                log_error("PREDICTOR", f"API请求失败 {attempt + 1}/3", str(e))
                if attempt == 2:
                    raise e
                time.sleep(2)

        result = response.json()
        log_api_response("PREDICTOR", result, result.get('choices', [{}])[0].get('message', {}).get('content', '')[:200] if result.get('choices') else "")

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            log_info("PREDICTOR", "Predictor调用成功", f"回复长度: {len(content)}")
            return content
        else:
            log_error("PREDICTOR", "API返回格式异常", json.dumps(result, ensure_ascii=False))
            return f"【API错误】{result}"

    except requests.exceptions.Timeout:
        log_error("PREDICTOR", "API请求超时", "timeout=60s")
        return f"【错误】API请求超时"
    except requests.exceptions.ConnectionError as e:
        log_error("PREDICTOR", "API连接失败", str(e))
        return f"【错误】连接失败: {str(e)}"
    except Exception as e:
        log_error("PREDICTOR", "Predictor调用异常", f"{str(e)}\n{traceback.format_exc()}")
        return f"【错误】{str(e)}"

def call_observer_api(conversation_history, role_content):
    """调用 Observer 分析对话质量"""
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            return {"error": "请在 config.json 中配置 API Key"}

        # 构建对话摘要
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content']}"
            for m in conversation_history
        ])

        system_prompt = """你是一个对话质量评估专家。请分析以下对话，评估 NPC 的回复质量。

角色设定：
{}

对话历史：
{}

请输出 JSON 格式的评估结果：
{{
  "scores": {{
    "logic": 1-5,
    "methodology": 1-5,
    "immersion": 1-10,
    "risk": 0-3
  }},
  "reviews": {{
    "character_consistency": "OK/ISSUE",
    "ooc_check": "OK/ISSUE",
    "beat_execution": "OK/ISSUE"
  }},
  "feedbacks": [
    {{
      "type": "praise/suggestion/warning/correction",
      "target": "评估项",
      "issue": "问题描述",
      "suggestion": "建议",
      "priority": "P0-P3"
    }}
  ],
  "summary": "一句话总结"
}}

只输出 JSON，不要其他内容。""".format(role_content, conv_text)

        url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": api_config.get('model', 'MiniMax-M2.5'),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请分析这段对话的质量"}
            ]
        }

        # 添加重试机制 (最多3次，每次间隔2秒)
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=60)
                break
            except Exception as e:
                if attempt == 2:
                    raise e
                time.sleep(2)

        result = response.json()

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            # 尝试解析 JSON
            try:
                return json.loads(content)
            except:
                return {"raw": content}
        else:
            return {"error": str(result)}

    except Exception as e:
        return {"error": str(e)}

def call_director_api(conversation_history, role_content, axes_data, event_card=None):
    """调用 Director (Narrative Director) 进行叙事决策"""
    try:
        api_config = CONFIG.get('api', {})
        api_key = api_config.get('api_key', '')

        if not api_key or api_key == "your-api-key-here":
            return {"error": "请在 config.json 中配置 API Key"}

        # 加载 Director 提示词
        director_prompt_path = os.path.join(os.path.dirname(__file__), "..", "roles", "director.md")
        if not os.path.exists(director_prompt_path):
            return {"error": f"找不到 Director 提示词文件: {director_prompt_path}"}

        with open(director_prompt_path, 'r', encoding='utf-8') as f:
            director_prompt = f.read()

        # 构建对话摘要
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content']}"
            for m in conversation_history[-5:]  # 最近5轮
        ])

        # 当前轴状态
        axes_text = "\n".join([
            f"- {k}: {v}" for k, v in axes_data.items()
        ])

        # 事件卡信息（包含 plot_hook）
        event_text = ""
        if event_card and (event_card.get("event_id") or event_card.get("title")):
            event_id = event_card.get('event_id', '')
            archetype = event_card.get('archetype', '')
            title = event_card.get('title', '')
            plot_hook = event_card.get('plot_hook', '')
            trigger = event_card.get('trigger', '')
            
            event_text = f"""
当前事件卡:
- event_id: {event_id}
- archetype: {archetype}
- title: {title}
- trigger: {trigger}
- plot_hook: {plot_hook}

【重要】请将事件卡的 plot_hook 填入 STORY_PATCH 的 focus 字段，作为本轮对话的重点。"""

        # 构建用户输入
        user_input = f"""## 当前角色设定
{role_content}

## 对话历史 (最近5轮)
{conv_text}

## 当前六轴状态
{axes_text}
{event_text}

## 任务
请根据上述信息，输出 STORY_PATCH 和 STATE_UPDATE。"""

        url = f"{api_config.get('base_url', 'https://api.minimax.chat/v1')}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": api_config.get('model', 'MiniMax-M2.5'),
            "messages": [
                {"role": "system", "content": director_prompt},
                {"role": "user", "content": user_input}
            ]
        }

        # 添加重试机制 (最多3次)
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=60)
                break
            except Exception as e:
                if attempt == 2:
                    return {"error": str(e)}
                time.sleep(2)

        result = response.json()

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            return {"raw": content}
        else:
            return {"error": str(result)}

    except Exception as e:
        return {"error": str(e)}
class NPCChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NPC Chat Prototype")
        self.root.geometry("1200x700")

        # 加载角色
        roles_path = CONFIG.get('roles_path', '')
        self.roles = load_npc_roles(roles_path)

        if not self.roles:
            messagebox.showerror("错误", "未找到任何 NPC 角色文件 (npc_*.md)")
            return

        # 对话历史
        self.conversation_history = []
        self.current_role_id = None

        # 各角色的输入输出（用于预览）
        self.director_input = ""
        self.director_output = ""
        self.predictor_input = ""
        self.predictor_output = ""
        self.performer_input = ""
        self.performer_output = ""

        # 六轴数据
        self.axes_data = {
            "Intimacy": 50,
            "Risk": 20,
            "Info": 30,
            "Action": 40,
            "Rel": 60,
            "Growth": 25
        }

        # 事件卡数据
        self.event_card = {
            "event_id": "",
            "archetype": "",
            "title": "",
            "trigger": "",
            "plot_hook": ""
        }

        # 引擎相关
        self.engine = None
        # 强制使用引擎模式，走三层架构

        self.setup_ui()

    def setup_ui(self):
        """创建 UI 组件"""
        # 顶部：角色选择 + 模型选择
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        # 角色选择
        ttk.Label(top_frame, text="角色:").pack(side=tk.LEFT)

        self.role_var = tk.StringVar()
        self.role_combo = ttk.Combobox(
            top_frame,
            textvariable=self.role_var,
            values=list(self.roles.keys()),
            state="readonly",
            width=20
        )
        self.role_combo.pack(side=tk.LEFT, padx=5)
        self.role_combo.bind('<<ComboboxSelected>>', self.on_role_selected)

        # 模型选择
        ttk.Label(top_frame, text="模型:").pack(side=tk.LEFT, padx=(20, 5))
        
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            top_frame,
            textvariable=self.model_var,
            state="readonly",
            width=20
        )
        self.model_combo.pack(side=tk.LEFT, padx=5)
        
        # 加载可用模型列表
        try:
            from engine_llm import get_available_models, set_model, MODELS_CONFIG
            available_models = get_available_models()
            log_info("GUI", f"MODELS_CONFIG加载", f"{MODELS_CONFIG}")
            log_info("GUI", f"可用模型列表", f"{available_models}")
            self.model_combo['values'] = available_models
            if available_models:
                self.model_var.set(available_models[0])
        except Exception as e:
            import traceback
            log_info("GUI", f"加载模型列表失败", f"{str(e)}")
        
        self.model_combo.bind('<<ComboboxSelected>>', self.on_model_selected)

        ttk.Button(top_frame, text="新对话", command=self.start_new_chat).pack(side=tk.LEFT, padx=10)

        # 按钮区域 - 放在顶部角色选择栏下方，独立一行，不受右侧面板挤压
        btn_top_frame = ttk.Frame(self.root, padding=(10, 5, 10, 0))
        btn_top_frame.pack(fill=tk.X)

        ttk.Button(btn_top_frame, text="发送", command=self.send_message).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_top_frame, text="保存", command=self.save_conversation).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_top_frame, text="分析", command=self.analyze_conversation).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_top_frame, text="新对话", command=self.start_new_chat).pack(side=tk.LEFT, padx=5)

        # 中间：使用 PanedWindow 分为三栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ============ 左侧：对话区域 ============
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)  # 左侧占 3 份

        self.chat_text = scrolledtext.ScrolledText(
            left_frame,
            wrap=tk.WORD,
            font=("Microsoft YaHei", 10)
        )
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # 输入区域
        bottom_frame = ttk.Frame(left_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.input_text = tk.Text(bottom_frame, height=3, font=("Microsoft YaHei", 10))
        self.input_text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=(0, 5))
        self.input_text.bind('<Return>', lambda e: self.send_message())

        # ============ 中间：各角色输入输出预览（标签页形式）============
        middle_frame = ttk.Frame(paned)
        paned.add(middle_frame, weight=2)  # 中间占 2 份

        # 创建标签页控件
        self.debug_notebook = ttk.Notebook(middle_frame)
        self.debug_notebook.pack(fill=tk.BOTH, expand=True)

        # Perception 标签页（放在最前面）
        self.perception_tab = ttk.Frame(self.debug_notebook)
        self.debug_notebook.add(self.perception_tab, text="Perception")
        self._create_debug_tab(self.perception_tab, "perception")

        # Director 标签页
        self.director_tab = ttk.Frame(self.debug_notebook)
        self.debug_notebook.add(self.director_tab, text="Director")
        self._create_debug_tab(self.director_tab, "director")

        # Predictor 标签页
        self.predictor_tab = ttk.Frame(self.debug_notebook)
        self.debug_notebook.add(self.predictor_tab, text="Predictor")
        self._create_debug_tab(self.predictor_tab, "predictor")

        # Performer 标签页
        self.performer_tab = ttk.Frame(self.debug_notebook)
        self.debug_notebook.add(self.performer_tab, text="Performer")
        self._create_debug_tab(self.performer_tab, "performer")

        # ============ 右侧：六轴状态 + 事件卡 ============
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)  # 右侧占 2 份

        # 六轴状态区域
        ttk.Label(right_frame, text="[六轴状态]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        axes_container = ttk.Frame(right_frame, relief=tk.GROOVE, borderwidth=1)
        axes_container.pack(fill=tk.X, pady=(0, 10))

        self.axis_labels = {}
        axis_names = ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]

        for axis_name in axis_names:
            row_frame = ttk.Frame(axes_container)
            row_frame.pack(fill=tk.X, padx=5, pady=2)

            # 标签显示轴名称
            ttk.Label(row_frame, text=f"{axis_name}:", width=10, anchor=tk.W).pack(side=tk.LEFT)

            # 进度条
            progress = ttk.Progressbar(row_frame, length=80, mode='determinate')
            progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            # 数值标签
            value_label = ttk.Label(row_frame, text="0", width=4)
            value_label.pack(side=tk.LEFT)

            self.axis_labels[axis_name] = {"progress": progress, "value": value_label}

        # 初始化六轴显示
        self.update_axes_display()

        # 事件卡区域
        ttk.Label(right_frame, text="[事件卡]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.event_card_text = tk.Text(
            right_frame,
            height=6,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#e8f4e8"
        )
        self.event_card_text.pack(fill=tk.BOTH, expand=True)
        self.event_card_text.config(state=tk.DISABLED)

        # 运行速度监控窗口
        ttk.Label(right_frame, text="[运行速度]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(5, 5))
        
        speed_frame = tk.Frame(right_frame)
        speed_frame.pack(fill=tk.BOTH, expand=True)
        
        self.speed_text = tk.Text(
            speed_frame,
            font=("Consolas", 8),
            wrap=tk.WORD,
            bg="#f0f0f0"
        )
        self.speed_text.pack(fill=tk.BOTH, expand=True)
        self.speed_text.config(state=tk.DISABLED)

        # 初始化事件卡显示
        self.update_event_card_display()

        # 状态栏
        self.status_var = tk.StringVar(value="请选择角色开始对话")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X)

        # 默认选择第一个角色
        if self.roles:
            self.role_combo.current(0)
            self.on_role_selected(None)

    def _create_debug_tab(self, parent, role_key):
        """创建单个调试标签页，包含输入和输出两个窗口"""
        # 输入窗口（显示发送给LLM的内容，区分system和user提示词）
        input_frame = ttk.LabelFrame(parent, text="【输入】发送给LLM的内容", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # 创建输入文本框（带滚动条）
        input_text = tk.Text(
            input_frame,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#e8f0f8"
        )
        input_scroll = ttk.Scrollbar(input_frame, orient="vertical", command=input_text.yview)
        input_text.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        input_text.pack(fill=tk.BOTH, expand=True)
        input_text.config(state=tk.DISABLED)

        # 输出窗口（显示LLM返回的结果）
        output_frame = ttk.LabelFrame(parent, text="【输出】LLM返回结果", padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True)

        # 创建输出文本框（带滚动条）
        output_text = tk.Text(
            output_frame,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#f0f8e8"
        )
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=output_text.yview)
        output_text.configure(yscrollcommand=output_scroll.set)
        output_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        output_text.pack(fill=tk.BOTH, expand=True)
        output_text.config(state=tk.DISABLED)

        # 存储引用
        if role_key == "perception":
            self.perception_input_text = input_text
            self.perception_output_text = output_text
        elif role_key == "director":
            self.director_input_text = input_text
            self.director_output_text = output_text
        elif role_key == "predictor":
            self.predictor_input_text = input_text
            self.predictor_output_text = output_text
        elif role_key == "performer":
            self.performer_input_text = input_text
            self.performer_output_text = output_text

    def _build_predictor_system_prompt(self, role_content, axes_data, conversation_history, user_message):

        # 六轴状态区域
        ttk.Label(right_frame, text="[六轴状态]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        axes_container = ttk.Frame(right_frame, relief=tk.GROOVE, borderwidth=1)
        axes_container.pack(fill=tk.X, pady=(0, 10))

        self.axis_labels = {}
        axis_names = ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]

        for axis_name in axis_names:
            row_frame = ttk.Frame(axes_container)
            row_frame.pack(fill=tk.X, padx=5, pady=2)

            # 标签显示轴名称
            ttk.Label(row_frame, text=f"{axis_name}:", width=10, anchor=tk.W).pack(side=tk.LEFT)

            # 进度条
            progress = ttk.Progressbar(row_frame, length=80, mode='determinate')
            progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            # 数值标签
            value_label = ttk.Label(row_frame, text="0", width=4)
            value_label.pack(side=tk.LEFT)

            self.axis_labels[axis_name] = {"progress": progress, "value": value_label}

        # 初始化六轴显示
        self.update_axes_display()

        # 事件卡区域
        ttk.Label(right_frame, text="[事件卡]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.event_card_text = tk.Text(
            right_frame,
            height=6,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#e8f4e8"
        )
        self.event_card_text.pack(fill=tk.BOTH, expand=True)
        self.event_card_text.config(state=tk.DISABLED)

        # 运行速度监控窗口
        ttk.Label(right_frame, text="[运行速度]", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(5, 5))
        
        speed_frame = tk.Frame(right_frame)
        speed_frame.pack(fill=tk.BOTH, expand=True)
        
        self.speed_text = tk.Text(
            speed_frame,
            font=("Consolas", 8),
            wrap=tk.WORD,
            bg="#f0f0f0"
        )
        self.speed_text.pack(fill=tk.BOTH, expand=True)
        self.speed_text.config(state=tk.DISABLED)

        # 初始化事件卡显示
        self.update_event_card_display()

        # 状态栏
        self.status_var = tk.StringVar(value="请选择角色开始对话")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X)

        # 默认选择第一个角色
        if self.roles:
            self.role_combo.current(0)
            self.on_role_selected(None)

    def on_role_selected(self, event):
        """角色选择变更"""
        role_id = self.role_var.get()
        self.current_role_id = role_id
        self.conversation_history = []
        self.chat_text.delete('1.0', tk.END)

        # 加载该角色的最近聊天历史
        self.load_chat_history(role_id)

        # 加载该角色的存档（六轴状态）
        self.load_role_state(role_id)

        # 重置预览框
        self.perception_input = ""
        self.perception_output = ""
        self.director_input = ""
        self.director_output = ""
        self.predictor_input = ""
        self.predictor_output = ""
        self.performer_input = ""
        self.performer_output = ""

        # 重置引擎，确保新角色使用正确的角色设定
        # 下次发送消息时会自动用新角色创建引擎
        self.engine = None
        self.append_system(f"【系统】已切换到角色: {role_id}，引擎已重置")
    
    def load_role_state(self, role_id):
        """加载角色存档中的六轴状态
        优先级：存档 > 角色配置 > 默认值
        """
        if not role_id:
            return

        # 存档路径
        save_dir = os.path.join(os.path.dirname(__file__), "..", "save")
        state_file = f"state_{role_id}.json"
        state_path = os.path.join(save_dir, state_file)

        # 1. 优先尝试加载存档
        if os.path.exists(state_path):
            try:
                import json
                with open(state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                axes = data.get("axes", {})
                if axes and all(0 <= v <= 10 for v in axes.values() if isinstance(v, (int, float))):
                    # 存档有效，直接使用
                    self.axes_data = {k: int(v) for k, v in axes.items()}
                    self.update_axes_display()
                    self.append_system(f"【系统】已加载角色存档，六轴: {self.axes_data}")
                    return
            except Exception as e:
                log_info("GUI", "加载存档失败", str(e))

        # 2. 存档无效或不存在，使用角色配置的值
        role = self.roles.get(role_id)
        if role and 'axes' in role:
            self.axes_data = role['axes'].copy()
            self.update_axes_display()
            self.append_system(f"【系统】使用角色配置六轴: {self.axes_data}")
            return

        # 3. 使用默认值
        self.axes_data = {
            "Intimacy": 5,
            "Risk": 2,
            "Info": 3,
            "Action": 4,
            "Rel": 6,
            "Growth": 2
        }
        self.update_axes_display()
        self.append_system(f"【系统】使用默认六轴: {self.axes_data}")
    
    def on_model_selected(self, event):
        """模型选择变更"""
        selected_model = self.model_var.get()
        log_info("GUI", "选择模型", f"选择了: {selected_model}")
        try:
            from engine_llm import set_model, get_current_model
            log_info("GUI", "切换前MODEL", f"当前MODEL: {get_current_model()}")
            set_model(selected_model)
            log_info("GUI", "切换后MODEL", f"设置后MODEL: {get_current_model()}")
            self.status_var.set(f"已切换模型: {selected_model}")
        except Exception as e:
            import traceback
            log_error("GUI", "切换模型失败", f"{str(e)}\n{traceback.format_exc()}")
    
    def load_chat_history(self, role_id):
        """加载指定角色的最近聊天历史"""
        if not role_id:
            return

        logs_path = CONFIG.get('logs_path', '')
        chat_file = os.path.join(logs_path, f"chat_{role_id}.txt")
        
        # 调试：打印加载信息
        print(f"[DEBUG load] role_id={role_id}, chat_file={chat_file}, exists={os.path.exists(chat_file)}")

        if not os.path.exists(chat_file):
            self.append_system(f"【系统】未找到历史记录: {chat_file}")
            return

        try:
            with open(chat_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                return

            self.append_system("【系统】正在加载最近聊天历史...")

            role = self.roles.get(role_id, {'name': 'NPC'})
            role_name = role.get('name', 'NPC')
            
            # 调试：打印角色名和日志文件
            print(f"[DEBUG] role_id={role_id}, role_name={role_name}")
            print(f"[DEBUG] chat_file={chat_file}")
            
            import re  # 导入正则模块
            
            # 按行解析，收集多行消息
            lines = content.split('\n')
            i = 0
            current_speaker = None
            current_msg_lines = []
            
            for line in lines:
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#') or line.startswith('='):
                    continue
                
                # 检测时间戳行 [时间] 用户: xxx 或 [时间] 角色名: xxx
                # 修复正则：秒部分用非捕获组
                ts_match = re.match(r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\]\s*(.+)$', line)
                if ts_match:
                    # 先保存上一条消息
                    if current_speaker and current_msg_lines:
                        msg_content = '\n'.join(current_msg_lines).strip()
                        if current_speaker == 'user':
                            self.chat_text.insert(tk.END, f"你: {msg_content}\n")
                            self.conversation_history.append({"role": "user", "content": msg_content})
                        else:
                            self.chat_text.insert(tk.END, f"{role_name}: {msg_content}\n")
                            self.conversation_history.append({"role": "assistant", "content": msg_content})
                    
                    # 开始新消息 - 去掉括号部分进行匹配
                    msg_part = ts_match.group(2)
                    # 去掉 (xxx) 格式的角色名后缀
                    clean_msg = re.sub(r'\s*\([^)]*\)\s*:', ':', msg_part)
                    
                    # 检查是否是用户消息
                    if clean_msg.startswith('用户:') or clean_msg.startswith('你:'):
                        current_speaker = 'user'
                        current_msg_lines = [clean_msg[clean_msg.find(':')+1:].strip()]
                    # 检查是否是NPC消息（去掉英文名后匹配）
                    elif '沈予曦' in clean_msg or '林星月' in clean_msg or 'linxingyue' in clean_msg.lower() or 'lin xingyue' in clean_msg.lower():
                        current_speaker = 'npc'
                        current_msg_lines = [clean_msg[clean_msg.find(':')+1:].strip()]
                    else:
                        current_speaker = None
                        current_msg_lines = []
                elif current_speaker and line:
                    # 继续收集消息内容（多行）
                    current_msg_lines.append(line)
            
            # 保存最后一条消息
            if current_speaker and current_msg_lines:
                msg_content = '\n'.join(current_msg_lines).strip()
                if current_speaker == 'user':
                    self.chat_text.insert(tk.END, f"你: {msg_content}\n")
                    self.conversation_history.append({"role": "user", "content": msg_content})
                else:
                    self.chat_text.insert(tk.END, f"{role_name}: {msg_content}\n")
                    self.conversation_history.append({"role": "assistant", "content": msg_content})

            self.chat_text.see(tk.END)
            rounds = len(self.conversation_history) // 2
            
            # 调试：打印解析结果
            print(f"[DEBUG] loaded {len(self.conversation_history)} messages")
            for i, msg in enumerate(self.conversation_history):
                print(f"  [{i}] {msg.get('role')}: {msg.get('content', '')[:30]}...")
            
            self.append_system(f"【系统】已加载 {rounds} 轮历史对话")

        except Exception as e:
            self.append_system(f"【系统】加载历史失败: {str(e)}")

    def start_new_chat(self):
        """开始新对话"""
        if self.current_role_id:
            self.conversation_history = []
            self.chat_text.delete('1.0', tk.END)
            self.append_system("【系统】对话已重置")

            # 重置预览框
            self.director_input = ""
            self.director_output = ""
            self.predictor_input = ""
            self.predictor_output = ""
            self.performer_input = ""
            self.performer_output = ""

            # 获取当前角色的六轴初始值
            role = self.roles.get(self.current_role_id)
            if role and 'axes' in role:
                self.axes_data = role['axes'].copy()  # 使用角色特定的六轴初始值
            else:
                self.axes_data = {
                    "Intimacy": 50,
                    "Risk": 20,
                    "Info": 30,
                    "Action": 40,
                    "Rel": 60,
                    "Growth": 25
                }

            self.event_card = {
                "event_id": "",
                "archetype": "",
                "title": "",
                "trigger": "",
                "plot_hook": ""
            }

            # 确保调用 update_axes_display
            self.update_axes_display()
            self.update_event_card_display()

            self.update_preview_panes()

    def append_message(self, role, content, model=""):
        """添加消息到显示区域
        Args:
            role: 角色名
            content: 对话内容
            model: 使用的模型名称（如 "doubao"）
        """
        if model and model != "MiniMax-M2.5":
            # 显示模型信息
            self.chat_text.insert(tk.END, f"\n{role} [{model}]: {content}\n")
        else:
            self.chat_text.insert(tk.END, f"\n{role}: {content}\n")
        self.chat_text.see(tk.END)

    def append_system(self, content):
        """添加系统消息"""
        self.chat_text.insert(tk.END, f"\n【系统】{content}\n")
        self.chat_text.see(tk.END)


    def update_preview_panes(self):
        """更新中间标签页预览框"""
        # 记录到日志
        log_info("GUI", "更新Perception预览", f"输入长度: {len(self.perception_input)}, 输出长度: {len(self.perception_output)}")
        log_info("GUI", "更新Director预览", f"输入长度: {len(self.director_input)}, 输出长度: {len(self.director_output)}")
        log_info("GUI", "更新Predictor预览", f"输入长度: {len(self.predictor_input)}, 输出长度: {len(self.predictor_output)}")
        log_info("GUI", "更新Performer预览", f"输入长度: {len(self.performer_input)}, 输出长度: {len(self.performer_output)}")
        
        # Perception 输入日志
        if self.perception_input:
            has_user_input = "用户输入" in self.perception_input
            log_info("GUI", f"Perception输入包含'用户输入': {has_user_input}", 
                    f"前500字符: {self.perception_input[:500]}")
            log_debug("GUI", "Perception输入内容", self.perception_input[:3000])
        
        # Perception 输出日志
        if self.perception_output:
            log_debug("GUI", "Perception输出内容", self.perception_output[:2000])
        
        # Director 输入日志（完整内容）
        if self.director_input:
            # 搜索关键字段
            has_perception = "用户输入分析" in self.director_input
            log_info("GUI", f"Director输入包含'用户输入分析': {has_perception}", 
                    f"前500字符: {self.director_input[:500]}")
            log_debug("GUI", "Director输入内容", self.director_input[:5000])
        
        # Director 输出日志（完整内容）
        if self.director_output:
            log_debug("GUI", "Director输出内容", self.director_output[:2000])
        
        # Predictor 输入日志
        if self.predictor_input:
            log_debug("GUI", "Predictor输入内容", self.predictor_input[:5000])
        
        # Predictor 输出日志
        if self.predictor_output:
            log_debug("GUI", "Predictor输出内容", self.predictor_output[:2000])
        
        # Performer 输入日志
        if self.performer_input:
            log_debug("GUI", "Performer输入内容", self.performer_input[:3000])
        
        # Performer 输出日志
        if self.performer_output:
            log_debug("GUI", "Performer输出内容", self.performer_output[:2000])
        
        # 更新 Perception 标签页
        self.perception_input_text.config(state=tk.NORMAL)
        self.perception_input_text.delete('1.0', tk.END)
        self.perception_input_text.insert('1.0', self.perception_input)
        self.perception_input_text.config(state=tk.DISABLED)

        self.perception_output_text.config(state=tk.NORMAL)
        self.perception_output_text.delete('1.0', tk.END)
        self.perception_output_text.insert('1.0', self.perception_output)
        self.perception_output_text.config(state=tk.DISABLED)

        # 更新 Director 标签页
        self.director_input_text.config(state=tk.NORMAL)
        self.director_input_text.delete('1.0', tk.END)
        self.director_input_text.insert('1.0', self.director_input)
        self.director_input_text.config(state=tk.DISABLED)

        self.director_output_text.config(state=tk.NORMAL)
        self.director_output_text.delete('1.0', tk.END)
        self.director_output_text.insert('1.0', self.director_output)
        self.director_output_text.config(state=tk.DISABLED)

        # 更新 Predictor 标签页
        self.predictor_input_text.config(state=tk.NORMAL)
        self.predictor_input_text.delete('1.0', tk.END)
        self.predictor_input_text.insert('1.0', self.predictor_input)
        self.predictor_input_text.config(state=tk.DISABLED)

        self.predictor_output_text.config(state=tk.NORMAL)
        self.predictor_output_text.delete('1.0', tk.END)
        self.predictor_output_text.insert('1.0', self.predictor_output)
        self.predictor_output_text.config(state=tk.DISABLED)

        # 更新 Performer 标签页
        self.performer_input_text.config(state=tk.NORMAL)
        self.performer_input_text.delete('1.0', tk.END)
        self.performer_input_text.insert('1.0', self.performer_input)
        self.performer_input_text.config(state=tk.DISABLED)

        self.performer_output_text.config(state=tk.NORMAL)
        self.performer_output_text.delete('1.0', tk.END)
        self.performer_output_text.insert('1.0', self.performer_output)
        self.performer_output_text.config(state=tk.DISABLED)

    def _build_predictor_system_prompt(self, role_content, axes_data, conversation_history, user_message):
        """构建 Predictor 的 system prompt"""
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
        recent_history = conversation_history[-5:]  # 最近5轮
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content'][:200]}"
            for m in recent_history
        ])

        axes_text = f"当前六轴状态: Intimacy={axes_data.get('Intimacy', 50)}, Risk={axes_data.get('Risk', 20)}, Info={axes_data.get('Info', 30)}, Action={axes_data.get('Action', 40)}, Rel={axes_data.get('Rel', 60)}, Growth={axes_data.get('Growth', 25)}"

        return f"""{predictor_prompt}

角色设定：
{role_content[:1500]}

当前六轴状态：
{axes_text}

最近对话：
{conv_text}

用户最新输入：
{user_message}

请输出 JSON 格式的事件卡。"""

    def _build_director_system_prompt(self, role_content, axes_data, conversation_history, event_card):
        """构建 Director 的 system prompt"""
        # 读取 director.md 提示词
        director_prompt_path = os.path.join(os.path.dirname(__file__), "..", "roles", "director.md")
        
        if os.path.exists(director_prompt_path):
            with open(director_prompt_path, 'r', encoding='utf-8') as f:
                director_prompt = f.read()
        else:
            director_prompt = """你是一个 Narrative Director（叙事指挥中枢）。

你需要根据对话历史和角色设定，输出 STORY_PATCH 来驱动表演模型。

输出格式（严格）：
===STORY_PATCH_BEGIN===
[STORY_PATCH]
- narrative_level: L0|L1|L2
- focus: （本轮重点体验，用自然语言）
- logic_subtext: （NPC 此时的心理潜台词）
- thread_to_touch: （若有，用 thread_id + 一句话）
- patch_status: 明确标注 [STALL / HOLD / EVOLVE / PIVOT]
- continuity_flag: 当状态为 HOLD 或 EVOLVE 时，此项为 true
- beat_plan: 1.反应拍、2.演进拍、3.钩子拍
- tension_tools: 工具A、工具B
- hook: （一个问题 或 二选一）
- hard_avoid: 禁止项列表
===STORY_PATCH_END===

===STATE_UPDATE_JSON===
{
  "driving_signals": { "initiative": x, "intent": "...", "affect": "...", "stall": x },
  "axes_next": { "Intimacy": x, "Risk": x, "Info": x, "Action": x, "Rel": x, "Growth": x },
  "momentum_next": { ... },
  "open_threads_next": [ ... ],
  "meta": { "priority_hit": "P0-P4", "level": "L0-L2" }
}
===STATE_UPDATE_END==="""

        # 构建对话摘要
        conv_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'NPC'}: {m['content']}"
            for m in conversation_history[-5:]  # 最近5轮
        ])

        # 当前轴状态
        axes_text = "\n".join([
            f"- {k}: {v}" for k, v in axes_data.items()
        ])

        # 事件卡信息（包含 plot_hook）
        event_text = ""
        if event_card and (event_card.get("event_id") or event_card.get("title")):
            event_id = event_card.get('event_id', '')
            archetype = event_card.get('archetype', '')
            title = event_card.get('title', '')
            plot_hook = event_card.get('plot_hook', '')
            trigger = event_card.get('trigger', '')
            
            event_text = f"""
当前事件卡:
- event_id: {event_id}
- archetype: {archetype}
- title: {title}
- trigger: {trigger}
- plot_hook: {plot_hook}

【重要】请将事件卡的 plot_hook 填入 STORY_PATCH 的 focus 字段，作为本轮对话的重点。"""

        return f"""{director_prompt}

## 当前角色设定
{role_content}

## 对话历史 (最近5轮)
{conv_text}

## 当前六轴状态
{axes_text}
{event_text}

## 任务
请根据上述信息，输出 STORY_PATCH 和 STATE_UPDATE。"""

    def update_axes_display(self):
        """更新六轴状态显示"""
        if not hasattr(self, 'axis_labels'):
            return

        for axis_name, value in self.axes_data.items():
            if axis_name in self.axis_labels:
                # 更新进度条
                self.axis_labels[axis_name]["progress"]["value"] = value
                # 更新数值标签
                self.axis_labels[axis_name]["value"].config(text=str(value))

    def update_event_card_display(self):
        """更新事件卡显示（直接显示原始 Predictor 输出）"""
        if not hasattr(self, 'event_card_text'):
            return

        self.event_card_text.config(state=tk.NORMAL)
        self.event_card_text.delete('1.0', tk.END)

        if self.event_card:
            # 检查是否是原始输出
            if self.event_card.get('_raw_output'):
                # 直接显示原始输出
                self.event_card_text.insert('1.0', self.event_card['_raw_output'])
            else:
                # 兼容旧格式：动态显示所有字段
                import json
                card_text = "【事件卡】\n"
                for key, value in self.event_card.items():
                    if value:
                        if isinstance(value, dict):
                            card_text += f"{key}:\n"
                            for k, v in value.items():
                                card_text += f"  - {k}: {v}\n"
                        elif isinstance(value, list):
                            card_text += f"{key}:\n"
                            for i, item in enumerate(value):
                                if isinstance(item, dict):
                                    card_text += f"  [{i+1}]\n"
                                    for k, v in item.items():
                                        card_text += f"    - {k}: {v}\n"
                                else:
                                    card_text += f"  - {item}\n"
                        else:
                            card_text += f"{key}: {value}\n"
                self.event_card_text.insert('1.0', card_text)
        else:
            self.event_card_text.insert('1.0', "等待事件触发...")

        self.event_card_text.config(state=tk.DISABLED)

    def update_axes_on_response(self, user_msg, npc_reply):
        """根据对话响应更新六轴数据"""
        import random

        # 模拟六轴变化（根据实际业务逻辑修改）
        # 所有轴范围：0-10
        # Intimacy: 亲密度，随对话增加
        self.axes_data["Intimacy"] = min(10, max(0, self.axes_data["Intimacy"] + random.randint(0, 2)))

        # Risk: 风险度，随对话波动
        self.axes_data["Risk"] = min(10, max(0, self.axes_data["Risk"] + random.randint(-1, 1)))

        # Info: 信息交换
        self.axes_data["Info"] = min(10, max(0, self.axes_data["Info"] + random.randint(0, 1)))

        # Action: 行动力
        self.axes_data["Action"] = min(10, max(0, self.axes_data["Action"] + random.randint(-1, 1)))

        # Rel: 关系
        self.axes_data["Rel"] = min(10, max(0, self.axes_data["Rel"] + random.randint(0, 1)))

        # Growth: 成长
        self.axes_data["Growth"] = min(10, max(0, self.axes_data["Growth"] + random.randint(0, 1)))

        # 更新显示
        self.update_axes_display()

    def parse_predictor_events(self, predictor_output, return_events=False):
        """解析 Predictor API 输出，提取事件卡（动态解析所有字段和所有事件）"""
        import re
        import json

        if not predictor_output or predictor_output.startswith("【"):
            return [] if return_events else None

        all_events = []
        
        try:
            # 查找 JSON 块
            json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', predictor_output)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = predictor_output

            data = json.loads(json_str)

            # 获取事件列表（支持多种字段名）
            events = data.get('events', []) or data.get('pending_events', []) or data.get('event_pool', [])
            
            # 解析所有事件
            for event in events:
                # 动态获取所有字段，不限定字段名
                event_dict = {}
                for key, value in event.items():
                    if value:  # 只保留非空字段
                        # 如果值是字典或列表，转为字符串
                        if isinstance(value, (dict, list)):
                            event_dict[key] = json.dumps(value, ensure_ascii=False)
                        else:
                            event_dict[key] = str(value)
                
                if event_dict:
                    all_events.append(event_dict)

            # 如果没有事件，检查根级别的字段（扁平格式）
            if not all_events:
                for key, value in data.items():
                    if value and key not in ['parse_error', 'raw', 'reason']:
                        if isinstance(value, (dict, list)):
                            data[key] = json.dumps(value, ensure_ascii=False)
                
                # 把根级别的非元数据字段也显示出来
                if data.get('event_id') or data.get('title'):
                    all_events.append({k: v for k, v in data.items() if v and k not in ['parse_error', 'raw', 'reason']})

            # 显示所有事件
            if all_events:
                display_text = "【事件卡】\n"
                for i, evt in enumerate(all_events):
                    display_text += f"\n=== 事件 {i+1} ===\n"
                    for key, value in evt.items():
                        display_text += f"{key}: {value}\n"
                
                self.event_card_text.config(state=tk.NORMAL)
                self.event_card_text.delete('1.0', tk.END)
                self.event_card_text.insert('1.0', display_text)
                self.event_card_text.config(state=tk.DISABLED)
                
                # 更新 event_card 字典（保留第一个事件的字段供其他地方使用）
                if all_events:
                    self.event_card = all_events[0]
                
                return all_events if return_events else None

        except json.JSONDecodeError:
            pass

        # 备用：简单文本解析
        try:
            # 尝试提取所有 key: value 格式的内容
            lines = predictor_output.split('\n')
            event_dict = {}
            current_key = None
            
            for line in lines:
                # 匹配 key: value 格式
                match = re.match(r'^([^:]+):\s*(.+)$', line.strip())
                if match:
                    key = match.group(1).strip()
                    value = match.group(2).strip()
                    if key and value:
                        event_dict[key] = value
            
            if event_dict:
                all_events.append(event_dict)
                display_text = "【事件卡】\n"
                for key, value in event_dict.items():
                    display_text += f"{key}: {value}\n"
                
                self.event_card_text.config(state=tk.NORMAL)
                self.event_card_text.delete('1.0', tk.END)
                self.event_card_text.insert('1.0', display_text)
                self.event_card_text.config(state=tk.DISABLED)
                
                self.event_card = event_dict
                
                return all_events if return_events else None

        except Exception as e:
            print(f"解析事件卡失败: {e}")

        return all_events if return_events else None

    def parse_director_focus(self, director_output):
        """解析 Director 输出，提取 focus 字段（包含事件卡的 plot_hook）"""
        import re
        
        if not director_output or director_output.startswith("【"):
            return ""
        
        try:
            # 尝试从 STORY_PATCH 中提取 focus 字段
            # 格式: - focus: （本轮重点体验，用自然语言）
            focus_match = re.search(r'focus:\s*\n?\s*([^-\n]+)', director_output, re.IGNORECASE)
            if focus_match:
                focus_text = focus_match.group(1).strip()
                # 清理可能的 markdown 格式
                focus_text = re.sub(r'^\[.*?\]\s*', '', focus_text)  # 去掉 [L1] 等前缀
                return focus_text
            
            # 备用：查找 focus 行的任何内容
            lines = director_output.split('\n')
            for line in lines:
                if 'focus' in line.lower() and ':' in line:
                    # 提取冒号后面的内容
                    focus_text = line.split(':', 1)[1].strip()
                    if focus_text:
                        return focus_text
            
        except Exception as e:
            print(f"解析 Director focus 失败: {e}")
        
        return ""

    def update_event_card_on_predictor(self):
        """根据 Predictor 输出更新事件卡"""
        # 实际事件卡更新由 parse_predictor_events 处理
        # 这里只保留接口兼容性，不需要再生成随机数据
        pass

    def send_message(self):
        """发送消息"""
        user_message = self.input_text.get('1.0', tk.END).strip()
        if not user_message:
            return

        if not self.current_role_id:
            messagebox.showwarning("提示", "请先选择角色")
            return

        # 清空输入框
        self.input_text.delete('1.0', tk.END)

        # 显示用户消息
        self.append_message("你", user_message)

        # 添加到历史
        self.conversation_history.append({"role": "user", "content": user_message})

        # 构建各角色的输入
        role = self.roles[self.current_role_id]

        # ========== 引擎模式 - 三层架构 ==========
        # 强制使用引擎模式，不再降级到传统模式
        
        # 按需初始化引擎（首次发送消息时）
        if not self.engine:
            # 构建角色状态文件路径
            state_file = f"state_{self.current_role_id}.json"
            save_path = os.path.join(os.path.dirname(__file__), "..", "save", state_file)
            
            log_info("ENGINE", f"检查状态文件: {save_path}")
            
            # 检查存档是否存在
            if os.path.exists(save_path):
                # 先创建引擎
                self.engine = create_engine()
                # 创建引擎后，重新应用当前模型设置
                from engine_llm import set_model, get_current_model
                current = get_current_model()
                if current != "MiniMax-M2.5":
                    set_model(current)
                
                # 存档存在，检查是否有效
                is_valid, reason = self.engine.state.validate_save_data(save_path)
                
                if is_valid:
                    # 有效存档，直接加载
                    log_info("ENGINE", "存档有效，加载状态")
                    # 不要重新创建引擎，直接加载
                    load_result = self.engine.state.load(save_path)
                    
                    if load_result:
                        # 同步引擎中的六轴到GUI显示
                        self.axes_data = {k: v for k, v in self.engine.state.axes.items()}
                        self.update_axes_display()
                        self.append_system(f"已加载历史状态，六轴: {self.engine.state.axes}")
                    else:
                        # 加载失败，询问用户
                        user_choice = messagebox.askyesno(
                            "Load Failed",
                            f"Role [{role['name']}] state load failed. Start new? (Yes=init, No=cancel)"
                        )
                        if not user_choice:
                            return  # 取消发送
                        # 选择是，执行初始化
                        start_engine(self.engine, self.current_role_id, role.get('content', '') if role else '')
                else:
                    # 无效存档，询问用户
                    user_choice = messagebox.askyesno(
                        "Invalid File",
                        f"Role [{role['name']}] state invalid: {reason}. Start new? (Yes=init, No=cancel)"
                    )
                    if not user_choice:
                        return  # 取消发送
                    # 选择是，执行初始化
                    self.engine = create_engine()
                    start_engine(self.engine, self.current_role_id, role.get('content', '') if role else '')
            else:
                # 无存档，执行完整初始化
                log_info("ENGINE", "无存档，执行初始化")
                self.engine = create_engine()
                start_engine(self.engine, self.current_role_id, role.get('content', '') if role else '')
            
            self.append_system(f"引擎已启动")
        
        # 引擎三层架构处理
        try:
            # 强制刷新日志
            import sys
            sys.stdout.flush()
            
            # 传递对话历史给引擎
            result = chat(self.engine, user_message, self.conversation_history)
                    
            # 强制刷新
            sys.stdout.flush()
                    
            log_info("GUI", f"引擎返回keys", f"{list(result.keys())}")
                    
            # 打印关键值
            p_in = result.get('perception_input', '')
            p_out = result.get('perception_output', '')
            d_in = result.get('director_input', '')
            d_out = result.get('director_output', {})
                    
            log_info("GUI", f"值检查", 
                f"perception_input长度={len(p_in)}, perception_output类型={type(p_out)}, "
                f"director_input长度={len(d_in)}, director_output类型={type(d_out)}")
                    
            # Director输入前200字符
            if d_in:
                log_info("GUI", f"Director输入前200", d_in[:200])
                    
            # 调试：打印result的键
            log_info("GUI", "引擎返回result的键", f"keys: {list(result.keys())}")
                    
            # 显示回复
            npc_reply = result.get('npc', '...')
            performer_model = result.get('performer_model', 'minimax')
            log_info("GUI", "performer_model", f"{performer_model}")
            # 简化模型名显示
            display_model = performer_model.split(':')[-1] if ':' in performer_model else performer_model
            if 'doubao' in performer_model:
                display_model = 'doubao'
            self.append_message(role['name'], npc_reply, display_model)
            self.conversation_history.append({"role": "assistant", "content": npc_reply})
            
            # 显示运行速度
            timing = result.get('timing', {})
            if timing:
                speed_info = "=== 运行速度 ===\n"
                for step, duration in timing.items():
                    speed_info += f"{step}: {duration}秒\n"
                self.speed_text.config(state=tk.NORMAL)
                self.speed_text.insert(tk.END, speed_info)
                self.speed_text.see(tk.END)
                self.speed_text.config(state=tk.DISABLED)
                    
            # 更新轴值显示 - 引擎返回的是0-10，直接使用（不再×10）
            axes = result.get('axes', {})
            self.axes_data = {k: v for k, v in axes.items()}  # 直接使用0-10
            self.update_axes_display()
                    
            # 更新事件卡显示 - 直接显示 Predictor 原始输出
            predictor_raw = result.get('predictor_raw_output', '')
            neh_triggered = result.get('neh_triggered')
            
            if predictor_raw:
                # 直接存储原始输出，显示完整 JSON
                self.event_card = {"_raw_output": predictor_raw}
            elif neh_triggered:
                # 显示触发的 NEH 事件
                self.event_card = {"_raw_output": str(neh_triggered)}
            
            if self.event_card:
                self.update_event_card_display()
                    
            # 更新预览面板 - 显示各模块输入输出
            # 先检查result的所有内容
            result_keys = list(result.keys())
            log_info("GUI", "引擎返回的keys", f"{result_keys}")
                    
            # 调试：打印完整的result结构
            log_info("GUI", "DEBUG-result结构", f"type={type(result)}, keys={result_keys}")
                    
            # Perception - 如果引擎没返回，就显示备用信息
            p_input = result.get('perception_input', '')
            p_output = result.get('perception_output', {})
                    
            # 如果为空，显示备用信息
            if not p_input:
                p_input = f"【调试】perception_input为空，可能是引擎模式未正确执行\n引擎返回keys: {result_keys}"
            if not p_output:
                p_output = {"note": "perception_output为空，可能是引擎模式未正确执行"}
                    
            log_info("GUI", "perception_input", f"长度: {len(p_input)}, 内容前100: {p_input[:100] if isinstance(p_input, str) else 'NOT_STRING'}")
                    
            # Perception显示LLM原始输出
            self.perception_input = p_input if isinstance(p_input, str) else str(p_input)
            self.perception_output = result.get('perception_raw_output', '')
                    
            # Director - 检查所有可用的键
            log_info("GUI", "result所有键", f"{list(result.keys())}")
                    
            self.director_input = result.get('director_input', '')
            # 如果director_input为空，尝试从perception构建
            if not self.director_input and p_output:
                # 从perception构建director输入
                perc = p_output if isinstance(p_output, dict) else {}
                self.director_input = f"【用户输入分析】\n{json.dumps(perc, ensure_ascii=False)}"
                log_info("GUI", "从perception构建director_input", self.director_input[:200])
                    
            # Director显示LLM原始输出
            self.director_output = result.get('director_raw_output', '')
                    
            # Predictor 显示LLM原始输出（从 engine 对象读取后台执行的结果）
            predictor_raw = result.get('predictor_raw_output', '')
            predictor_in = result.get('predictor_input', '')
            
            # 检查 engine 对象是否有后台执行的 Predictor 结果
            predictor_event = None
            if hasattr(self.engine, '_last_predictor_output') and self.engine._last_predictor_output:
                predictor_raw = self.engine._last_predictor_output
                predictor_in = getattr(self.engine, '_last_predictor_input', '')
                predictor_event = getattr(self.engine, '_last_predictor_event', None)
            
            if predictor_raw:
                self.predictor_input = predictor_in
                self.predictor_output = predictor_raw
                # 更新事件卡显示
                if predictor_event:
                    self.event_card = {"_raw_output": predictor_raw}
                    self.update_event_card_display()
            else:
                self.predictor_input = f"Round {result.get('round', 0)} - 事件卡后台异步生成"
                self.predictor_output = "本轮未生成事件卡"
                    
            # Performer 显示LLM原始输出
            self.performer_input = result.get('performer_input', '')
            self.performer_output = result.get('performer_raw_output', '')
                    
            self.update_preview_panes()
            self.status_var.set(f"引擎模式: {role['name']}")
                    
            # 自动保存对话
            self.auto_save_conversation()
            
            # 保存引擎状态（六轴、动量、线程等）到角色专属文件
            try:
                save_path = os.path.join(os.path.dirname(__file__), "..", "save", f"state_{self.current_role_id}.json")
                save_state(self.engine, save_path)
            except Exception as e:
                print(f"[DEBUG] 保存状态失败: {e}")
                    
            return
                
        except Exception as e:
            # 引擎模式错误直接抛出，不再降级
            raise Exception(f"引擎错误: {e}")
    
    def auto_save_conversation(self):
        """自动保存对话到文件（每个角色一份，持续追加）"""
        if not self.conversation_history or not self.current_role_id:
            return

        logs_path = CONFIG.get('logs_path', '')
        os.makedirs(logs_path, exist_ok=True)

        # 按角色 ID 命名文件，例如: chat_linxingyue.txt
        filename = os.path.join(logs_path, f"chat_{self.current_role_id}.txt")
        
        # 调试
        print(f"[DEBUG save] role_id={self.current_role_id}, filename={filename}")
        print(f"[DEBUG save] history count={len(self.conversation_history)}")

        role = self.roles.get(self.current_role_id, {'name': 'Unknown'})

        # 检查文件是否存在，决定是否写入标题行
        file_exists = os.path.exists(filename)

        with open(filename, 'a', encoding='utf-8') as f:
            # 如果是新文件，写入标题行
            if not file_exists:
                f.write(f"# 对话记录 - {role['name']}\n")
                f.write(f"# 角色ID: {self.current_role_id}\n")
                f.write(f"# 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")

            # 写入本轮对话（只写入最新的2条：用户消息 + NPC回复）
            recent_msgs = self.conversation_history[-2:] if len(self.conversation_history) >= 2 else self.conversation_history
            for msg in recent_msgs:
                role_name = "用户" if msg['role'] == 'user' else role['name']
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {role_name}: {msg['content']}\n\n")

    def save_conversation(self):
        """保存对话到文件"""
        if not self.conversation_history:
            messagebox.showwarning("提示", "没有对话内容可保存")
            return

        logs_path = CONFIG.get('logs_path', '')
        os.makedirs(logs_path, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(logs_path, f"chat_{timestamp}.txt")

        role = self.roles.get(self.current_role_id, {'name': 'Unknown'})

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"角色: {role['name']}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")

            for msg in self.conversation_history:
                role_name = "用户" if msg['role'] == 'user' else role['name']
                f.write(f"{role_name}: {msg['content']}\n\n")

        messagebox.showinfo("保存成功", f"对话已保存到:\n{filename}")

    def analyze_conversation(self):
        """调用 Observer 分析对话"""
        if not self.conversation_history:
            messagebox.showwarning("提示", "没有对话可供分析")
            return

        if not self.current_role_id:
            messagebox.showwarning("提示", "请先选择角色")
            return

        self.status_var.set("正在分析对话...")
        self.root.update()

        role = self.roles[self.current_role_id]
        result = call_observer_api(self.conversation_history, role['content'])

        # 显示分析结果
        self.append_system("【Observer 分析结果】")

        if 'error' in result:
            self.append_system(f"分析失败: {result['error']}")
        else:
            # 显示评分
            scores = result.get('scores', {})
            self.append_system(
                f"逻辑:{scores.get('logic','-')}/5 | "
                f"方法论:{scores.get('methodology','-')}/5 | "
                f"沉浸感:{scores.get('immersion','-')}/10 | "
                f"风险:{scores.get('risk','-')}/3"
            )

            # 显示总结
            summary = result.get('summary', '')
            if summary:
                self.append_system(f"总结: {summary}")

            # 显示反馈
            feedbacks = result.get('feedbacks', [])
            if feedbacks:
                self.append_system("反馈:")
                for fb in feedbacks[:3]:  # 最多显示3条
                    self.append_system(
                        f"  [{fb.get('type','')}] {fb.get('target','')}: {fb.get('suggestion','')}"
                    )

        self.status_var.set("分析完成")

# ============= 主程序 =============
def main():
    root = tk.Tk()
    app = NPCChatApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
