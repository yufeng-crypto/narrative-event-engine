# -*- coding: utf-8 -*-
"""
爱巴基斯坦叙事引擎 (aibaji Engine) - v3.0
按 ENGINE_CORE.md v3.0 实现的统一核心引擎

架构：
- Session State Manager: 唯一状态枢纽
- Initializer: 场景初始化
- Perception Layer: 用户输入解析
- Director Layer: 数值计算 + STORY_PATCH生成
- Performer Layer: 对话渲染
- NEH-Predictor: 事件卡生成
- NEH-EventPool: 事件池管理
- NEH-Trigger: 触发判定
"""

import sys
import json
import os
import time
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

# ==================== 配置 ====================
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"api_key": "", "api_url": "", "model": "MiniMax-M2.5"}

def load_models_config():
    """加载模型配置"""
    # 从 engine 目录往上一级查找
    base_dir = os.path.dirname(os.path.dirname(__file__))  # logic/
    config_path = os.path.join(base_dir, "models_config.json")
    log_path = os.path.join(base_dir, "prototype", "logs", "debug", "engine_load.log")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        with open(log_path, 'w', encoding='utf-8') as logf:
            logf.write(f"[load_models_config] 成功加载: {config}\n")
        return config
    except Exception as e:
        with open(log_path, 'w', encoding='utf-8') as logf:
            logf.write(f"[load_models_config] 加载失败: {e}, path={config_path}\n")
        return {"default": "minimax", "providers": {}}

# 加载配置
CONFIG = load_config()
MODELS_CONFIG = load_models_config()
API_KEY = CONFIG.get("api_key", "")
API_URL = CONFIG.get("api_url", "https://api.minimax.chat/v1/text/chatcompletion_v2")
MODEL = CONFIG.get("model", "MiniMax-M2.5")

# 当前使用的provider
CURRENT_PROVIDER = "minimax"

def get_available_models():
    """获取可用的模型列表"""
    models = []
    for provider_name, provider_config in MODELS_CONFIG.get("providers", {}).items():
        for model in provider_config.get("models", []):
            models.append(f"{provider_name}:{model}")
    return models

def set_model(provider_model: str):
    """设置当前使用的模型
    Args:
        provider_model: 格式如 "minimax:MiniMax-M2.5" 或 "doubao:doubao-lite-4k"
    """
    global CURRENT_PROVIDER, MODEL

    if ":" in provider_model:
        provider, model = provider_model.split(":", 1)
        CURRENT_PROVIDER = provider
        MODEL = model
    else:
        MODEL = provider_model

    # 调试日志
    log_to_file(f"[set_model] MODEL={MODEL}, CURRENT_PROVIDER={CURRENT_PROVIDER}")

    # 注意：不修改全局 API_URL，只修改 MODEL
    # API_URL 的选择会在 call_llm 中根据 model 参数动态决定

def get_current_provider_config():
    """获取当前provider的配置"""
    return MODELS_CONFIG.get("providers", {}).get(CURRENT_PROVIDER, {})

def get_current_model():
    """获取当前使用的模型名称"""
    return MODEL

# ==================== 常量定义 ====================
AXES = ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]
DEFAULT_MAX_AXIS = 8
MAX_THREADS = 8
MAX_EVENTS = 10
NEH_INTERVAL = 1  # 调试模式：每轮都执行

INTENT_TYPES = ["Story", "Chat", "Verify", "Conflict", "Meta"]
EMOTION_TONES = ["Warm", "Teasing", "Neutral", "Pensive", "Sad", "Vulnerable",
                 "Fearful", "Cold", "Annoyed", "Hostile"]
DOMINANCE_TYPES = ["User-Led", "NPC-Led", "Balanced"]

# ==================== 张力工具库 ====================
TENSION_TOOLS = {
    "Intimacy": {
        "0-2": ["社交安全距离", "称谓固化", "眼神公事化", "礼貌性客气"],
        "3-7": ["微碰触", "眼神躲闪", "推拉回复", "私人领地入侵"],
        "8-10": ["禁忌共鸣", "逻辑断裂", "脆弱点袒露", "感官剥夺", "主权烙印", "宿命式交付", "界限消融", "静谧狂欢"]
    },
    "Risk": {
        "0-2": ["逻辑自洽", "常态维持", "秩序确认", "安全话题兜底"],
        "3-7": ["环境阴影", "异样声响", "逻辑裂痕", "被监视感"],
        "8-10": ["物理环境崩溃", "致命倒计时", "强制二选一", "不可逆伤损"]
    },
    "Info": {
        "0-2": ["标准简报", "官方回避", "事实堆砌", "假性配合"],
        "3-7": ["只说一半", "隐晦线索", "回避式反问", "假性公开"],
        "8-10": ["话到嘴边改口", "被打断的解释", "高价真相", "认知重构线索"]
    },
    "Action": {
        "0-2": ["静止坐姿", "程序化位移", "背景化互动", "任务驱动"],
        "3-7": ["位置位移", "目标引导", "中途阻碍", "转场暗示"],
        "8-10": ["场景强行切换", "资源体力耗尽", "决定性打击", "物理围困"]
    },
    "Rel": {
        "0-2": ["职业性尊重", "边界声明", "利益对等", "身份标签"],
        "3-7": ["权力试探", "轻微质疑", "身份暗示", "非正式契约"],
        "8-10": ["阵营对质", "背叛契机", "忠诚度测试", "绝对臣服", "绝对对等"]
    },
    "Growth": {
        "0-2": ["话术面具", "舒适圈维持", "公众形象锚定", "拒绝内省"],
        "3-7": ["内心独白碎念", "信仰微调", "旧忆闪回", "自我怀疑"],
        "8-10": ["核心信仰崩塌", "性格面具破碎", "决定性牺牲", "身份彻底觉醒"]
    }
}

# ==================== NEH 母版库 (32个) ====================
NEH_ARCHETYPES = {
    "ARC_W_01": {"name": "不速之客", "trigger": "Risk > 6 且 Action < 4"},
    "ARC_W_02": {"name": "社交破裂", "trigger": "Risk > 5 且 Rel < 4"},
    "ARC_W_03": {"name": "紧急召唤", "trigger": "Action > 5 且 Initiative = 0"},
    "ARC_W_04": {"name": "资源争夺", "trigger": "Action > 6 且 Risk > 4"},
    "ARC_W_05": {"name": "舆论风暴", "trigger": "Risk > 7 且 Info < 5"},
    "ARC_E_01": {"name": "物理囚笼", "trigger": "Intimacy > 4 且 Action > 6"},
    "ARC_E_02": {"name": "资产损毁", "trigger": "Action > 5 且 Risk > 5"},
    "ARC_E_03": {"name": "场景崩塌", "trigger": "Action > 7 且 Initiative = 1"},
    "ARC_E_04": {"name": "失物寻找", "trigger": "Info < 4 且 Action > 5"},
    "ARC_E_05": {"name": "感官侵蚀", "trigger": "Intimacy > 5 且 Risk < 4"},
    "ARC_E_06": {"name": "突发灾害", "trigger": "Risk >= 7 且 Action >= 5"},
    "ARC_E_07": {"name": "场地危机", "trigger": "Risk >= 6 且 Action >= 4"},
    "ARC_E_08": {"name": "强制转移", "trigger": "Action >= 7 且 Rel >= 3"},
    "ARC_R_01": {"name": "致命误会", "trigger": "Intimacy > 6 且 Info < 4"},
    "ARC_R_02": {"name": "秘密外溢", "trigger": "Info > 6 且 Growth < 5"},
    "ARC_R_03": {"name": "旧识干预", "trigger": "Risk > 6 且 Intimacy > 5"},
    "ARC_R_04": {"name": "信任余震", "trigger": "Rel > 5 且 Risk > 6"},
    "ARC_R_05": {"name": "依赖转移", "trigger": "Intimacy > 7 且 Action < 3"},
    "ARC_R_06": {"name": "情敌突袭", "trigger": "Intimacy >= 5 且 Rel >= 4"},
    "ARC_R_07": {"name": "工作干扰", "trigger": "Action >= 4 且 Risk >= 3"},
    "ARC_R_08": {"name": "意外访客", "trigger": "Intimacy >= 3 且 Info <= 2"},
    "ARC_R_09": {"name": "信息错位", "trigger": "Info >= 5 且 Risk >= 4"},
    "ARC_R_10": {"name": "行为误解", "trigger": "Intimacy >= 4 且 Rel <= 5"},
    "ARC_R_11": {"name": "第三方挑拨", "trigger": "Risk >= 6 且 Info >= 4"},
    "ARC_S_01": {"name": "梦想受挫", "trigger": "Growth > 7 且 Risk > 6"},
    "ARC_S_02": {"name": "终极二选一", "trigger": "Growth > 8 且 Intimacy > 7"},
    "ARC_S_03": {"name": "面具剥落", "trigger": "Growth > 9 且 Info > 7"},
    "ARC_S_04": {"name": "价值背离", "trigger": "Risk > 8 且 Rel > 6"},
    "ARC_S_05": {"name": "余烬重塑", "trigger": "Growth = 10"},
    "ARC_S_06": {"name": "利益冲突", "trigger": "Growth >= 5 且 Rel >= 4"},
    "ARC_S_07": {"name": "情感抉择", "trigger": "Intimacy >= 6 且 Growth >= 4"},
    "ARC_S_08": {"name": "成长抉择", "trigger": "Growth >= 7 且 Risk >= 5"},
}

# ==================== 数据类 ====================
@dataclass
class PerceptionResult:
    initiative: int = 1
    intent: str = "Chat"
    emotion_tone: str = "Neutral"
    stall: int = 0
    dominance: str = "Balanced"
    hidden_meaning: str = ""
    timing_detail: dict = field(default_factory=dict)

@dataclass
class StoryPatch:
    level: str = "P4"
    focus: str = ""
    subtext: str = ""
    beat_plan: str = "HOLD"
    tension_tools: List[str] = field(default_factory=list)
    hook: str = ""
    forbidden: List[str] = field(default_factory=list)

@dataclass
class NEHEvent:
    event_id: str = ""
    archetype: str = ""
    archetype_id: str = ""
    trigger_condition: Dict = field(default_factory=dict)
    impact: Dict = field(default_factory=dict)
    priority: int = 2
    description: str = ""
    created_at: int = 0

@dataclass
class Thread:
    id: str = ""
    label: str = ""
    status: str = "open"
    priority: int = 2

# ==================== LLM 调用 ====================
def call_llm(messages: List[Dict], max_tokens: int = 1024, max_retries: int = 3, model: str = None) -> str:
    """调用LLM
    Args:
        messages: 对话消息列表
        max_tokens: 最大token数
        max_retries: 最大重试次数
        model: 指定模型（如果不指定则使用全局MODEL）
    """
    # 如果没有指定模型，默认使用 minimax
    use_model = model if model else "MiniMax-M2.5"

    log_to_file(f"[call_llm] 调用模型={use_model}, 传入model参数={model}")

    last_error = ""
    for attempt in range(max_retries):
        try:
            import urllib.request
            import urllib.error

            payload = {"model": use_model, "messages": messages, "temperature": 0.7}
            data = json.dumps(payload).encode('utf-8')

            # 获取对应的 API URL
            api_url = API_URL
            api_key = API_KEY
            # 如果指定了非 minimax 的模型，查找对应的配置
            if model and model != "MiniMax-M2.5":
                # 提取纯模型名（去掉provider前缀，如 "doubao:xxx" -> "xxx"）
                pure_model = model.split(":", 1)[-1] if ":" in model else model
                for provider_name, provider_config in MODELS_CONFIG.get("providers", {}).items():
                    if pure_model in provider_config.get("models", []):
                        api_url = provider_config.get("api_url", API_URL)
                        api_key = provider_config.get("api_key", API_KEY)
                        log_to_file(f"[call_llm] 切换到 {provider_name}: {api_url}")
                        break

            req = urllib.request.Request(api_url, data=data, method='POST')
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")

            try:
                response = urllib.request.urlopen(req, timeout=60)
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8') if e.fp else ""
                return f"[HTTP错误 {e.code}: {e.reason}] {error_body[:200]}"

            result = json.loads(response.read().decode('utf-8'))

            if "base_resp" in result and result["base_resp"].get("status_code", 0) != 0:
                return f"[API错误: {result['base_resp']}]"

            if "reply" in result and result["reply"]:
                return result["reply"]

            choices = result.get("choices", [])
            if choices and len(choices) > 0:
                return choices[0].get("message", {}).get("content", "")

            return f"[API返回空: {result}]"

        except urllib.error.URLError as e:
            last_error = f"网络错误: {e.reason}"
            time.sleep(2 ** attempt)
        except json.JSONDecodeError as e:
            return f"[JSON解析错误: {e}]"
        except Exception as e:
            return f"[LLM调用失败: {e}]"

    return f"[重试{max_retries}次后仍失败: {last_error}]"

# ==================== 日志 ====================
def log_to_file(message: str):
    """写日志到文件"""
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "prototype", "logs", "debug")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "engine_debug.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            from datetime import datetime
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except:
        pass

# ==================== Prompt加载 ====================
def load_prompt(prompt_name: str) -> str:
    """从roles目录加载Prompt文件"""
    prompt_file = os.path.join(os.path.dirname(__file__), "..", "roles", f"{prompt_name}.md")
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"[找不到{prompt_name}.md]"
    except Exception as e:
        return f"[加载{prompt_name}失败: {e}]"

def merge_system_messages(messages: List[Dict]) -> List[Dict]:
    system_contents = []
    other_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            system_contents.append(msg.get("content", ""))
        else:
            other_messages.append(msg)
    if system_contents:
        combined = "\n\n---\n\n".join(system_contents)
        return [{"role": "system", "content": combined}] + other_messages
    return messages

# ==================== 工具函数 ====================
def get_role_prompt(role_name: str) -> str:
    role_file = os.path.join(os.path.dirname(__file__), "..", "roles", f"{role_name}.md")
    try:
        with open(role_file, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return ""

def get_npc_context(npc_name: str) -> str:
    return get_role_prompt(f"npc_{npc_name}") or f"你是{npc_name}，请根据角色设定回复。"

def parse_with_schema(text: str, schema_type: str = "generic") -> dict:
    if not text or not text.strip():
        return {"parse_error": True, "raw": "", "reason": "empty_input"}

    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(json_block_pattern, text, re.IGNORECASE)
    if match:
        try:
            return {"parse_error": False, "data": json.loads(match.group(1).strip()), "strategy": "json_block"}
        except:
            pass

    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return {"parse_error": False, "data": json.loads(text[start:end+1]), "strategy": "bare_json"}
        except:
            pass

    return {"parse_error": True, "raw": text[:500], "reason": "parse_failed"}

def clamp_axis(value: int, max_val: int = DEFAULT_MAX_AXIS) -> int:
    return max(0, min(max_val, value))

def apply_axis_damping(current: int, delta: int) -> int:
    if current >= 7:
        damping = (current - 7) / 4
        return int(delta * (1 - damping))
    return delta

def generate_id(prefix: str = "") -> str:
    return f"{prefix}{random.randint(10000000, 99999999)}"

# ==================== Session State Manager ====================
class SessionStateManager:
    """唯一状态枢纽"""
    def __init__(self):
        self.axes = {axis: 2 for axis in AXES}
        self.axes["Rel"] = 1
        self.momentum = {axis: 0 for axis in AXES}
        self.threads: List[Thread] = []
        self.event_pool: List[NEHEvent] = []
        self.round = 0
        self.initiative_history: List[int] = []
        self.npc_name = "沈予曦"
        self.character_profile = ""
        self.scene_archive = ""
        self.history = []

    def get_state(self) -> dict:
        return {
            "axes": self.axes.copy(),
            "momentum": self.momentum.copy(),
            "threads": [asdict(t) for t in self.threads],
            "event_pool": [asdict(e) for e in self.event_pool],
            "round": self.round,
            "avg_initiative": self.get_avg_initiative(),
            "npc_name": self.npc_name
        }

    def update_axes(self, changes: Dict[str, int]):
        for axis, delta in changes.items():
            if axis not in self.axes:
                continue
            delta = apply_axis_damping(self.axes[axis], delta)
            if axis == "Intimacy":
                max_intimacy = self.axes.get("Rel", 0) + 2
                new_val = clamp_axis(self.axes[axis] + delta)
                self.axes[axis] = min(new_val, max_intimacy)
            else:
                self.axes[axis] = clamp_axis(self.axes[axis] + delta)
            if delta > 0:
                self.momentum[axis] = min(2, self.momentum[axis] + 1)
            elif delta < 0:
                self.momentum[axis] = max(-2, self.momentum[axis] - 1)

    def add_initiative(self, initiative: int):
        self.initiative_history.append(initiative)
        if len(self.initiative_history) > 3:
            self.initiative_history = self.initiative_history[-3:]

    def get_avg_initiative(self) -> float:
        if not self.initiative_history:
            return 1.0
        return sum(self.initiative_history) / len(self.initiative_history)

    def save(self, filepath: str = None) -> str:
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "..", "save", "session_state.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {
            "axes": self.axes, "momentum": self.momentum,
            "threads": [asdict(t) for t in self.threads],
            "event_pool": [asdict(e) for e in self.event_pool],
            "round": self.round, "initiative_history": self.initiative_history,
            "npc_name": self.npc_name, "character_profile": self.character_profile,
            "scene_archive": self.scene_archive,
            "history": self.history,  # 保存对话历史
            "saved_at": datetime.now().isoformat()
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    def load(self, filepath: str = None) -> bool:
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "..", "save", "session_state.json")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.axes = data.get("axes", self.axes)
            self.momentum = data.get("momentum", self.momentum)
            self.threads = [Thread(**t) for t in data.get("threads", [])]
            self.event_pool = [NEHEvent(**e) for e in data.get("event_pool", [])]
            self.round = data.get("round", 0)
            self.initiative_history = data.get("initiative_history", [])
            self.npc_name = data.get("npc_name", "沈予曦")
            self.character_profile = data.get("character_profile", "")
            self.scene_archive = data.get("scene_archive", "")
            self.history = data.get("history", [])  # 恢复对话历史
            return True
        except:
            return False

    def validate_save_data(self, filepath: str = None) -> tuple:
        """检查存档数据是否有效
        返回: (is_valid: bool, reason: str)
        """
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "..", "save", "session_state.json")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            return False, "文件无法读取或格式错误"

        # 检查 axes
        axes = data.get("axes", {})
        if not axes:
            return False, "缺少六轴数据"
        for axis_name in ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]:
            if axis_name not in axes:
                return False, f"缺少轴: {axis_name}"
            val = axes[axis_name]
            if not isinstance(val, int) or val < 0 or val > 10:
                return False, f"轴 {axis_name} 值无效: {val}"

        # 检查 momentum
        momentum = data.get("momentum", {})
        if momentum:
            for axis_name in ["Intimacy", "Risk", "Info", "Action", "Rel", "Growth"]:
                if axis_name in momentum:
                    val = momentum[axis_name]
                    if not isinstance(val, int) or val < -2 or val > 2:
                        return False, f"动量 {axis_name} 值无效: {val}"

        # 检查 round
        round_val = data.get("round", -1)
        if not isinstance(round_val, int) or round_val < 0:
            return False, f"轮次数值无效: {round_val}"

        # 检查 npc_name
        npc_name = data.get("npc_name", "")
        if not npc_name or not isinstance(npc_name, str):
            return False, "NPC名称无效"

        # 检查 scene_archive
        scene_archive = data.get("scene_archive", "")
        if not scene_archive or not isinstance(scene_archive, str):
            return False, "场景档案无效"

        return True, "有效"

# ==================== 初始化专家 ====================
class Initializer:
    """初始化专家"""
    def __init__(self, state: SessionStateManager):
        self.state = state

    def initialize(self, npc_name: str, character_profile: str = "") -> dict:
        self.state.npc_name = npc_name
        self.state.character_profile = character_profile or get_npc_context(npc_name)
        scene_archive = self._generate_scene_archive()
        self.state.scene_archive = scene_archive
        self._set_initial_axes()
        first_patch = self._generate_first_patch()
        return {
            "scene_archive": scene_archive,
            "initial_axes": self.state.axes.copy(),
            "first_patch": asdict(first_patch)
        }

    def _generate_scene_archive(self) -> str:
        npc_ctx = self.state.character_profile[:500]
        prompt = f"""生成150字内场景档案，包含:中段切入、五感锚点、脆弱性瞬间。
NPC: {npc_ctx}
直接输出场景文字。"""
        result = call_llm([{"role": "user", "content": prompt}])
        return result[:200] if result else "场景初始化中..."

    def _set_initial_axes(self):
        self.state.axes = {"Intimacy": 2, "Risk": 3, "Info": 3, "Action": 2, "Rel": 4, "Growth": 5}

    def _generate_first_patch(self) -> StoryPatch:
        return StoryPatch(level="P4", focus="初次相遇", subtext="用户在观察NPC",
                         beat_plan="HOLD", tension_tools=["社交安全距离"], hook="NPC注意到用户了吗？")

# ==================== 感知层 ====================
class PerceptionLayer:
    """感知层"""
    def __init__(self, state: SessionStateManager):
        self.state = state
        self.prompt_template = load_prompt("perception")
        self._last_full_prompt = ""  # 保存最后一次使用的完整prompt

    def get_last_full_prompt(self) -> str:
        """返回最后一次使用的完整prompt（用于调试显示）"""
        return self._last_full_prompt

    def get_last_prompt_parts(self) -> dict:
        """返回system和user两部分prompt，用于GUI显示"""
        return {
            "system": getattr(self, '_last_system_prompt', ''),
            "user": getattr(self, '_last_user_prompt', '')
        }

    def get_last_llm_output(self) -> str:
        """返回LLM原始输出，用于GUI调试显示"""
        return getattr(self, '_last_llm_output', '')

    def analyze(self, user_input: str, last_npc_output: str = "") -> PerceptionResult:
        import time
        t0 = time.time()

        npc_ctx = self.state.character_profile[:300] or get_npc_context(self.state.npc_name)[:300]
        t1 = time.time()

        history = self._get_recent_history()
        t2 = time.time()

        # system prompt: md模板
        system_prompt = self.prompt_template

        # user prompt: 参数
        user_prompt = f"""NPC设定:
{npc_ctx}

对话历史:
{history}

用户输入: {user_input}

请输出JSON。"""

        # 保存两部分prompt用于调试显示
        self._last_system_prompt = system_prompt
        self._last_user_prompt = user_prompt
        self._last_full_prompt = f"===== SYSTEM =====\n{system_prompt}\n\n===== USER =====\n{user_prompt}"

        result = call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        # 保存原始输出用于调试显示
        self._last_llm_output = result
        
        parsed = parse_with_schema(result, "perception")

        if not parsed.get("parse_error"):
            data = parsed.get("data", {})
            return PerceptionResult(
                initiative=data.get("initiative", 1),
                intent=data.get("intent", "Chat"),
                emotion_tone=data.get("emotion_tone", "Neutral"),
                stall=data.get("stall", 0),
                dominance=data.get("dominance", "Balanced"),
                hidden_meaning=data.get("hidden_meaning", "")
            )
        return PerceptionResult()

    def _get_recent_history(self) -> str:
        if not self.state.history:
            return "（暂无历史）"
        recent = self.state.history[-10:]
        return "\n".join([f"用户: {h.get('user','')}\nNPC: {h.get('npc','')}" for h in recent])

# ==================== NEH EventPool ====================
class NEHEventPool:
    def __init__(self, max_size: int = MAX_EVENTS):
        self.events: List[NEHEvent] = []
        self.max_size = max_size

    def add(self, event: NEHEvent):
        if len(self.events) >= self.max_size:
            low_priority = [e for e in self.events if e.priority == 3]
            if low_priority:
                self.events.remove(min(low_priority, key=lambda x: x.created_at))
            else:
                self.events.pop(0)
        event.created_at = int(time.time())
        self.events.append(event)

    def remove_triggered(self, event_id: str):
        self.events = [e for e in self.events if e.event_id != event_id]

    def cleanup_low_priority(self, current_round: int):
        if current_round % 10 == 0:
            self.events = [e for e in self.events if e.priority != 3]

    def get_all(self) -> List[dict]:
        return [asdict(e) for e in self.events]

# ==================== NEH Trigger ====================
def check_neh_trigger(event_pool: List[NEHEvent], axes: dict, user_initiative: float) -> Optional[NEHEvent]:
    triggered = None
    for event in event_pool:
        if _evaluate_condition(event.trigger_condition, axes, user_initiative):
            if triggered is None or event.priority < triggered.priority:
                triggered = event
    return triggered

def _evaluate_condition(condition: dict, axes: dict, initiative: float) -> bool:
    for key, op_value in condition.items():
        current = initiative if key == "initiative" else axes.get(key, 0)
        if isinstance(op_value, str):
            if ">=" in op_value:
                _, val = op_value.split(">=")
                if current < int(val): return False
            elif ">" in op_value:
                _, val = op_value.split(">")
                if current <= int(val): return False
            elif "=" in op_value:
                _, val = op_value.split("=")
                if current != int(val): return False
    return True

# ==================== NEH Predictor ====================
class NEHPredictor:
    def __init__(self, state: SessionStateManager):
        self.state = state
        self.prompt_template = load_prompt("predictor")
        self._last_full_prompt = ""  # 保存最后一次使用的完整prompt

    def get_last_full_prompt(self) -> str:
        """返回最后一次使用的完整prompt（用于调试显示）"""
        return self._last_full_prompt

    def get_last_prompt_parts(self) -> dict:
        """返回system和user两部分prompt，用于GUI显示"""
        return {
            "system": getattr(self, '_last_system_prompt', ''),
            "user": getattr(self, '_last_user_prompt', '')
        }

    def get_last_llm_output(self) -> str:
        """返回LLM原始输出，用于GUI调试显示"""
        return getattr(self, '_last_llm_output', '')

    def generate_event_card(self) -> Optional[NEHEvent]:
        axes_str = json.dumps(self.state.axes, ensure_ascii=False)
        avg_init = self.state.get_avg_initiative()

        # 获取对话历史（最近10轮）
        history_str = ""
        if self.state.history:
            for h in self.state.history[-10:]:
                history_str += f"用户: {h.get('user', '')}\nNPC: {h.get('npc', '')}\n"

        # system prompt: md模板
        system_prompt = self.prompt_template

        # user prompt: 参数
        user_prompt = f"""对话历史（最近10轮）:
{history_str}

当前六轴:
{axes_str}

用户主动性均值:
{avg_init:.1f}

只输出JSON。"""

        # 保存两部分prompt用于调试显示
        self._last_system_prompt = system_prompt
        self._last_user_prompt = user_prompt
        self._last_full_prompt = f"===== SYSTEM =====\n{system_prompt}\n\n===== USER =====\n{user_prompt}"

        result = call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        
        # 保存原始输出用于调试显示
        self._last_llm_output = result
        
        parsed = parse_with_schema(result, "neh_event")

        if not parsed.get("parse_error"):
            data = parsed.get("data", {})
            # 支持嵌套格式 pending_events 或扁平格式
            pending = data.get("pending_events", [])
            if pending and len(pending) > 0:
                evt = pending[0]
                return NEHEvent(
                    event_id=evt.get("event_id", generate_id("neh_")),
                    archetype=evt.get("archetype_ref", evt.get("archetype", "")),
                    archetype_id=evt.get("archetype_id", ""),
                    trigger_condition=evt.get("trigger_condition", {}),
                    impact=evt.get("impact", {}),
                    priority=data.get("priority", 2),
                    description=evt.get("plot_hook", evt.get("description", ""))
                )
            else:
                return NEHEvent(
                    event_id=data.get("event_id", generate_id("neh_")),
                    archetype=data.get("archetype", ""),
                    archetype_id=data.get("archetype_id", ""),
                    trigger_condition=data.get("trigger_condition", {}),
                    impact=data.get("impact", {}),
                    priority=data.get("priority", 2),
                    description=data.get("description", "")
                )
        return None

# ==================== 导演层 ====================
class DirectorLayer:
    def __init__(self, state: SessionStateManager):
        self.state = state
        self.prompt_template = load_prompt("director")
        self._last_state_update = None
        self._last_full_prompt = ""  # 保存最后一次使用的完整prompt

    def get_last_full_prompt(self) -> str:
        """返回最后一次使用的完整prompt（用于调试显示）"""
        return self._last_full_prompt

    def get_last_prompt_parts(self) -> dict:
        """返回system和user两部分prompt，用于GUI显示"""
        return {
            "system": getattr(self, '_last_system_prompt', ''),
            "user": getattr(self, '_last_user_prompt', '')
        }

    def get_last_llm_output(self) -> str:
        """返回LLM原始输出，用于GUI调试显示"""
        return getattr(self, '_last_llm_output', '')

    def direct(self, perception: PerceptionResult, neh_event: Optional[NEHEvent] = None) -> StoryPatch:
        # 调试：打印当前轴值
        print(f"[Director] 当前轴值: {self.state.axes}")

        # 如果有NEH事件触发，也应用其影响
        if neh_event and neh_event.impact:
            axes_change = neh_event.impact.get("axes_change", {})
            if axes_change:
                self.state.update_axes(axes_change)
                print(f"[Director] NEH影响: {axes_change}")

        # 轴值变化现在由Director的LLM输出STATE_UPDATE决定，不再用硬编码
        # 调用LLM生成STORY_PATCH
        patch = self._generate_story_patch_with_llm(perception, neh_event)

        # 调试：打印STATE_UPDATE
        print(f"[Director] STATE_UPDATE: {self._last_state_update}")

        return patch

    def _calculate_axis_changes(self, perception: PerceptionResult) -> Dict[str, int]:
        """计算轴向变化"""
        changes = {}
        if perception.initiative == 0:
            changes["Action"] = -1
        elif perception.initiative >= 2:
            changes["Action"] = 1

        if perception.stall >= 2:
            changes["Action"] = changes.get("Action", 0) + 1
            changes["Info"] = changes.get("Info", 0) + 1

        return changes

    def _generate_story_patch_with_llm(self, perception: PerceptionResult, neh_event: Optional[NEHEvent] = None) -> StoryPatch:
        """调用LLM生成STORY_PATCH"""
        import time
        t0 = time.time()

        axes = self.state.axes
        axes_str = json.dumps(axes, ensure_ascii=False)
        t1 = time.time()

        momentum_str = json.dumps(self.state.momentum, ensure_ascii=False)
        t2 = time.time()

        threads_str = json.dumps([asdict(t) for t in self.state.threads], ensure_ascii=False)
        t3 = time.time()

        # 获取对话历史（最近10轮）
        history_str = ""
        if self.state.history:
            for h in self.state.history[-10:]:
                history_str += f"用户: {h.get('user', '')}\nNPC: {h.get('npc', '')}\n"
        t4 = time.time()

        # 角色设定
        npc_context = self.state.character_profile or get_npc_context(self.state.npc_name)
        t5 = time.time()

        # 感知结果
        perception_str = json.dumps({
            "initiative": perception.initiative,
            "intent": perception.intent,
            "emotion_tone": perception.emotion_tone,
            "stall": perception.stall,
            "dominance": perception.dominance,
            "hidden_meaning": perception.hidden_meaning
        }, ensure_ascii=False)

        # 调试：打印perception_str
        print(f"[Director] perception_str: {perception_str}")

        # NEH事件信息
        neh_info = ""
        if neh_event:
            neh_info = f"""
当前NEH事件:
- 母版: {neh_event.archetype}
- 描述: {neh_event.description}
- 触发条件: {json.dumps(neh_event.trigger_condition, ensure_ascii=False)}
"""

        # system prompt: md模板
        system_prompt = self.prompt_template

        # user prompt: 参数
        user_prompt = f"""角色设定:
{npc_context[:800]}

对话历史（最近10轮）:
{history_str}

当前六轴:
{axes_str}

动量:
{momentum_str}

线程池:
{threads_str}

用户输入分析:
{perception_str}
{neh_info}

请输出JSON格式。"""

        # 调试：打印prompt前200字符
        print(f"[Director] prompt前200字符: {user_prompt[:200]}")

        # 保存两部分prompt用于调试显示
        self._last_system_prompt = system_prompt
        self._last_user_prompt = user_prompt
        self._last_full_prompt = f"===== SYSTEM =====\n{system_prompt}\n\n===== USER =====\n{user_prompt}"

        result = call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        # 保存原始输出用于调试显示
        self._last_llm_output = result

        # 调试：打印原始输出
        print(f"[Director] LLM原始输出: {result[:500]}...")

        # ===== 解析两部分内容 =====
        # 1. 提取 STORY_PATCH 部分
        story_patch_str = ""
        story_match = re.search(r'===STORY_PATCH_BEGIN===(.*?)===STORY_PATCH_END===', result, re.DOTALL)
        if story_match:
            story_patch_str = story_match.group(1).strip()
            print(f"[Director] 提取到STORY_PATCH: {story_patch_str[:200]}...")

        # 2. 提取 STATE_UPDATE_JSON 部分
        state_update = {}
        state_match = re.search(r'===STATE_UPDATE_JSON===(.*?)===STATE_UPDATE_END===', result, re.DOTALL)
        if state_match:
            try:
                state_update = json.loads(state_match.group(1).strip())
                print(f"[Director] 提取到STATE_UPDATE: {state_update}")
            except:
                print(f"[Director] STATE_UPDATE JSON解析失败")

        # 保存state_update供后续使用
        self._last_state_update = state_update
        self._last_story_patch_str = story_patch_str

        # 如果提取到了STORY_PATCH，使用它
        if story_patch_str:
            # 简单解析STORY_PATCH内容
            patch = self._parse_story_patch(story_patch_str)
            return patch

        # 如果没提取到，尝试解析JSON
        parsed = parse_with_schema(result, "story_patch")
        if not parsed.get("parse_error"):
            data = parsed.get("data", {})
            story_patch_data = data.get("STORY_PATCH", data)
            patch = StoryPatch(
                level=story_patch_data.get("level", story_patch_data.get("narrative_level", "P4")),
                focus=story_patch_data.get("focus", "")[:50],
                subtext=story_patch_data.get("logic_subtext", story_patch_data.get("subtext", ""))[:50],
                beat_plan=story_patch_data.get("patch_status", story_patch_data.get("beat_plan", "HOLD")),
                tension_tools=story_patch_data.get("tension_tools", [])[:3],
                hook=story_patch_data.get("hook", ""),
                forbidden=story_patch_data.get("hard_avoid", story_patch_data.get("forbidden", []))
            )
            # 记录详细耗时
            self._timing_detail = {
                "获取轴和动量": round(t1-t0, 2),
                "获取线程": round(t3-t2, 2),
                "获取历史": round(t4-t3, 2),
                "获取角色上下文": round(t5-t4, 2),
                "构建Prompt": round(t6-t5, 2),
                "LLM调用": round(t7-t6, 2),
            }
            return patch

        # 解析失败返回默认值
        print(f"[Director] 使用备用生成器")
        return self._generate_story_patch_fallback(perception, neh_event)

    @property
    def timing_detail(self):
        return getattr(self, '_timing_detail', {})

    def apply_state_update(self):
        """应用STATE_UPDATE到状态"""
        if hasattr(self, '_last_state_update') and self._last_state_update:
            # 优先使用axes_next（绝对值）
            axes_next = self._last_state_update.get("axes_next", {})
            if axes_next:
                print(f"[Director.apply] 应用axes_next(绝对值): {axes_next}")
                for axis, value in axes_next.items():
                    if axis in AXES:
                        self.state.axes[axis] = int(value)
            else:
                # 如果没有axes_next，使用axis_changes（变化值）
                axis_changes = self._last_state_update.get("axis_changes", {})
                if axis_changes:
                    print(f"[Director.apply] 应用axis_changes(变化值): {axis_changes}")
                    for axis, delta in axis_changes.items():
                        if axis in AXES:
                            current = self.state.axes.get(axis, 0)
                            self.state.axes[axis] = max(0, min(10, current + int(delta)))

            # 应用动量变化
            momentum_next = self._last_state_update.get("momentum_next", {})
            if momentum_next:
                print(f"[Director.apply] 应用momentum_next: {momentum_next}")
                for axis, value in momentum_next.items():
                    if axis in AXES:
                        self.state.momentum[axis] = value

            # 打印更新后的轴值
            print(f"[Director.apply] 更新后轴值: {self.state.axes}")

            # 清理
            self._last_state_update = None

    def _parse_story_patch(self, story_patch_str: str) -> StoryPatch:
        """解析STORY_PATCH字符串"""
        # 从格式如 "- pacing_constraint: xxx" 中提取值
        def extract_field(key: str) -> str:
            pattern = rf'- {key}:?\s*(.+?)(?:\n|- |\Z)'
            match = re.search(pattern, story_patch_str, re.DOTALL)
            return match.group(1).strip() if match else ""

        focus = extract_field("focus")
        logic_subtext = extract_field("logic_subtext")

        # patch_mode 可能包含多行
        patch_mode_match = re.search(r'- patch_mode:(.+?)(?:- |===|\Z)', story_patch_str, re.DOTALL)
        patch_mode = patch_mode_match.group(1).strip() if patch_mode_match else "HOLD"

        beat_plan = extract_field("beat_plan")

        # tension_tools 可能是多行
        tools_match = re.search(r'- tension_tools:(.+?)(?:- |===|\Z)', story_patch_str, re.DOTALL)
        tension_tools = []
        if tools_match:
            tools_str = tools_match.group(1)
            # 提取工具名称
            for tool in re.findall(r'「([^」]+)」', tools_str):
                tension_tools.append(tool)

        hook = extract_field("hook")

        # continuity_requirement
        cont_match = re.search(r'- continuity_requirement:\s*(true|false)', story_patch_str, re.IGNORECASE)

        # hard_avoid
        avoid_match = re.search(r'- hard_avoid:(.+?)(?:- |===|\Z)', story_patch_str, re.DOTALL)
        forbidden = []
        if avoid_match:
            avoid_str = avoid_match.group(1)
            # 提取列表项
            for item in re.findall(r'[-·]\s*([^：\n]+)', avoid_str):
                forbidden.append(item.strip())

        return StoryPatch(
            level="P4",
            focus=focus[:50] if focus else "对话中",
            subtext=logic_subtext[:50] if logic_subtext else "正常对话",
            beat_plan=beat_plan[:100] if beat_plan else "HOLD",
            tension_tools=tension_tools[:3],
            hook=hook[:100] if hook else "接下来怎么做？",
            forbidden=forbidden[:5]
        )

    def _generate_story_patch_fallback(self, perception: PerceptionResult, neh_event: Optional[NEHEvent] = None) -> StoryPatch:
        """备用：生成默认STORY_PATCH"""
        axes = self.state.axes

        # 选择张力工具
        tools = []
        for axis in AXES:
            val = axes.get(axis, 0)
            if val <= 2:
                tier = "0-2"
            elif val <= 7:
                tier = "3-7"
            else:
                tier = "8-10"
            if axis in TENSION_TOOLS and tier in TENSION_TOOLS[axis]:
                tools.append(TENSION_TOOLS[axis][tier][0])

        # 确定节拍
        beat = "HOLD"
        if perception.stall >= 2:
            beat = "EVOLVE"

        focus = neh_event.description if neh_event else perception.hidden_meaning or "常规对话"

        return StoryPatch(
            level="P3" if neh_event else "P4",
            focus=focus[:50],
            subtext=perception.hidden_meaning[:50],
            beat_plan=beat,
            tension_tools=tools[:3],
            hook="下一句想说什么？"
        )
        axes = self.state.axes

        # 选择张力工具
        tools = []
        for axis in AXES:
            val = axes.get(axis, 0)
            if val <= 2:
                tier = "0-2"
            elif val <= 7:
                tier = "3-7"
            else:
                tier = "8-10"
            if axis in TENSION_TOOLS and tier in TENSION_TOOLS[axis]:
                tools.append(TENSION_TOOLS[axis][tier][0])

        # 确定节拍
        beat = "HOLD"
        if perception.stall >= 2:
            beat = "EVOLVE"

        focus = neh_event.description if neh_event else perception.hidden_meaning or "常规对话"

        return StoryPatch(
            level="P3" if neh_event else "P4",
            focus=focus[:50],
            subtext=perception.hidden_meaning[:50],
            beat_plan=beat,
            tension_tools=tools[:3],
            hook="下一句想说什么？"
        )

# ==================== 表现层 ====================
class PerformerLayer:
    """表现层"""
    def __init__(self, state: SessionStateManager):
        self.state = state
        self.prompt_template = load_prompt("performer")
        self._last_full_prompt = ""  # 保存最后一次使用的完整prompt

    def get_last_full_prompt(self) -> str:
        """返回最后一次使用的完整prompt（用于调试显示）"""
        return self._last_full_prompt

    def get_last_prompt_parts(self) -> dict:
        """返回system和user两部分prompt，用于GUI显示"""
        return {
            "system": getattr(self, '_last_system_prompt', ''),
            "user": getattr(self, '_last_user_prompt', '')
        }

    def get_last_llm_output(self) -> str:
        """返回LLM原始输出，用于GUI调试显示"""
        return getattr(self, '_last_llm_output', '')

    def perform(self, user_input: str, patch: StoryPatch, story_patch_str: str = "") -> str:
        """表现层：根据STORY_PATCH生成NPC对话
        Args:
            user_input: 用户输入
            patch: 解析后的StoryPatch对象
            story_patch_str: Director输出的原始STORY_PATCH字符串（可选，用于更精确的解析）
        """
        import time
        t0 = time.time()

        npc_ctx = self.state.character_profile or get_npc_context(self.state.npc_name)
        t1 = time.time()

        axes_str = json.dumps(self.state.axes, ensure_ascii=False)
        t2 = time.time()

        # system prompt: md模板
        system_prompt = self.prompt_template

        # 如果有原始字符串，优先使用STORY_PATCH
        story_patch_for_performer = story_patch_str if story_patch_str else json.dumps(asdict(patch), ensure_ascii=False)

        # user prompt: 参数
        user_prompt = f"""角色设定:
{npc_ctx[:600]}

六轴: {axes_str}

STORY_PATCH:
{story_patch_for_performer}

用户输入:
{user_input}

直接输出角色对话。"""

        t3 = time.time()

        # 保存两部分prompt用于调试显示
        self._last_system_prompt = system_prompt
        self._last_user_prompt = user_prompt
        self._last_full_prompt = f"===== SYSTEM =====\n{system_prompt}\n\n===== USER =====\n{user_prompt}"

        # 使用get_current_model()获取当前模型
        current_model = get_current_model()
        log_to_file(f"[performer.perform] 调用call_llm, current_model={current_model}")

        # Performer 使用可配置的模型
        result = call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], model=current_model)  # 传入当前配置的模型

        # 保存原始输出用于调试显示
        self._last_llm_output = result

        # 尝试解析JSON，如果失败则返回原始结果
        try:
            parsed = parse_with_schema(result, "performer")
            if not parsed.get("parse_error"):
                data = parsed.get("data", {})
                # 尝试提取dialogue字段
                if "dialogue" in data:
                    dialogue = data["dialogue"]
                    if isinstance(dialogue, dict):
                        # 组合reaction + evolution + hook
                        parts = []
                        if "reaction" in dialogue:
                            parts.append(dialogue["reaction"])
                        if "evolution" in dialogue:
                            parts.append(dialogue["evolution"])
                        if "hook" in dialogue:
                            parts.append(dialogue["hook"])
                        npc_output = "\n".join(parts)
                    elif isinstance(dialogue, str):
                        npc_output = dialogue
                else:
                    npc_output = result
            else:
                npc_output = result if result else "[NPC沉默]"
        except:
            npc_output = result if result else "[NPC沉默]"

        # 记录详细耗时
        self._timing_detail = {
            "获取角色上下文": round(t1-t0, 2),
            "获取轴数据": round(t2-t1, 2),
            "构建Prompt": round(t3-t2, 2),
        }

        return npc_output

# ==================== Observer 观察者 ====================
class ObserverLayer:
    """观察者：评估对话质量"""
    def __init__(self, state: SessionStateManager):
        self.state = state

    def evaluate(self, conversation_history: List[dict], npc_reply: str) -> dict:
        """评估对话质量"""
        npc_ctx = self.state.character_profile or get_npc_context(self.state.npc_name)

        # 构建历史
        history_str = ""
        for h in conversation_history[-5:]:
            role = "用户" if h.get('role') == 'user' else "NPC"
            history_str += f"{role}: {h.get('content', '')[:100]}\n"

        prompt = f"""你是对话质量评估专家。请分析以下对话，评估NPC的回复质量。

## 角色设定
{npc_ctx[:500]}

## 对话历史
{history_str}

## NPC最新回复
{npc_reply[:200]}

## 评估维度
1. 角色一致性：NPC回复是否符合角色设定
2. 情绪表达：情绪是否自然、多变
3. 三段式节拍：是否有反应拍→演进拍→钩子
4. 五感细节：是否包含感官细节
5. 出戏问题：是否有系统暴露、跳脱时间线等

请输出JSON格式：
{{
    "scores": {{
        "character_consistency": 1-10,
        "emotion_expression": 1-10,
        "beat_execution": 1-10,
        "immersion": 1-10
    }},
    "issues": ["问题1", "问题2"],
    "summary": "一句话总结"
}}

只输出JSON。"""

        result = call_llm([{"role": "user", "content": prompt}])
        parsed = parse_with_schema(result, "observer")

        if not parsed.get("parse_error"):
            return parsed.get("data", {})

        return {"summary": "评估失败", "scores": {}}

# ==================== 引擎核心 ====================
class Engine:
    """叙事引擎核心"""
    def __init__(self):
        self.state = SessionStateManager()
        self.event_pool = NEHEventPool()
        self.initializer = Initializer(self.state)
        self.perception = PerceptionLayer(self.state)
        self.director = DirectorLayer(self.state)
        self.performer = PerformerLayer(self.state)
        self.predictor = NEHPredictor(self.state)
        self.observer = ObserverLayer(self.state)
        print("=== aibaji Engine v3.0 ===")

    def start(self, npc_name: str, character_profile: str = "") -> dict:
        """初始化引擎"""
        result = self.initializer.initialize(npc_name, character_profile)
        print(f"[初始化] NPC: {npc_name}")
        print(f"[场景] {result['scene_archive'][:50]}...")
        return result

    def run_turn(self, user_input: str, conversation_history: list = None) -> dict:
        """执行一轮对话
        Args:
            user_input: 用户输入
            conversation_history: 对话历史列表 [{"role": "user"/"assistant", "content": "..."}]
        """
        import time
        timing = {}
        t0 = time.time()

        self.state.round += 1
        round_num = self.state.round

        print(f"\n=== Round {round_num} ===")
        print(f"用户: {user_input}")

        # 如果传入了对话历史，同步到引擎state
        if conversation_history:
            # 转换格式：GUI的conversation_history到引擎的state.history
            engine_history = []
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    engine_history.append({"user": content, "npc": ""})
                elif role == "assistant":
                    # 最后一轮的assistant补充到上一轮的npc
                    if engine_history and not engine_history[-1].get("npc"):
                        engine_history[-1]["npc"] = content
                    else:
                        engine_history.append({"user": "", "npc": content})
            # 更新引擎的history
            self.state.history = engine_history[-10:]  # 保留最近10轮

        # ===== 感知层 =====
        t1 = time.time()
        perception = self.perception.analyze(user_input)
        timing['perception'] = round(time.time() - t1, 2)
        
        # 收集感知层详细耗时
        if hasattr(perception, 'timing_detail') and perception.timing_detail:
            for k, v in perception.timing_detail.items():
                timing[f'  {k}'] = v
        
        self.state.add_initiative(perception.initiative)
        print(f"[感知] initiative={perception.initiative}, intent={perception.intent}, stall={perception.stall}")

        # 获取Perception使用的完整prompt（用于调试显示）
        # 获取各模块的输入（包含system和user两部分）
        perception_parts = self.perception.get_last_prompt_parts()
        perception_input = perception_parts.get("system", "") + "\n\n===== USER =====\n" + perception_parts.get("user", "")
        # Perception的输出就是perception对象
        perception_output = asdict(perception)

        # ===== NEH-Predictor (每5轮) =====
        predictor_input = ""
        predictor_output = None
        if round_num % NEH_INTERVAL == 0:
            new_event = self.predictor.generate_event_card()
            if new_event:
                predictor_output = asdict(new_event)
                self.event_pool.add(new_event)
                print(f"[NEH] 生成事件: {new_event.archetype}")

        # 获取Predictor使用的完整prompt（用于调试显示）
        predictor_parts = self.predictor.get_last_prompt_parts()
        predictor_input = predictor_parts.get("system", "") + "\n\n===== USER =====\n" + predictor_parts.get("user", "")

        # ===== NEH-Trigger =====
        triggered = check_neh_trigger(self.event_pool.events, self.state.axes, self.state.get_avg_initiative())
        if triggered:
            print(f"[NEH] 触发事件: {triggered.archetype}")
            self.event_pool.remove_triggered(triggered.event_id)

        # ===== 导演层 =====
        t2 = time.time()
        patch = self.director.direct(perception, triggered)
        timing['director'] = round(time.time() - t2, 2)

        # 收集导演层详细耗时
        if hasattr(self.director, 'timing_detail') and self.director.timing_detail:
            for k, v in self.director.timing_detail.items():
                timing[f'  {k}'] = v

        # 收集导演层详细耗时
        if hasattr(self.director, 'timing_detail') and self.director.timing_detail:
            for k, v in self.director.timing_detail.items():
                timing[f'  {k}'] = v

        # 获取Director提取的原始STORY_PATCH字符串（用于GUI显示）
        story_patch_str = getattr(self.director, '_last_story_patch_str', "")
        # 如果有原始STORY_PATCH，显示原始内容；否则显示解析后的JSON
        if story_patch_str:
            director_output = story_patch_str
        else:
            director_output = json.dumps(asdict(patch), ensure_ascii=False, indent=2)

        print(f"[导演] beat={patch.beat_plan}, focus={patch.focus}")

        # 获取Director使用的完整prompt（用于调试显示）
        director_parts = self.director.get_last_prompt_parts()
        director_input = director_parts.get("system", "") + "\n\n===== USER =====\n" + director_parts.get("user", "")

        # ===== 表现层 =====
        # 获取Director提取的原始STORY_PATCH字符串
        story_patch_str = getattr(self.director, '_last_story_patch_str', "")
        t3 = time.time()
        npc_output = self.performer.perform(user_input, patch, story_patch_str)
        timing['performer'] = round(time.time() - t3, 2)

        # 收集表现层详细耗时
        if hasattr(self.performer, 'timing_detail') and self.performer.timing_detail:
            for k, v in self.performer.timing_detail.items():
                timing[f'  {k}'] = v

        # 收集表现层详细耗时
        if hasattr(self.performer, 'timing_detail') and self.performer.timing_detail:
            for k, v in self.performer.timing_detail.items():
                timing[f'  {k}'] = v

        print(f"[NPC] {npc_output[:50]}...")

        # 获取Performer使用的完整prompt（用于调试显示）
        performer_parts = self.performer.get_last_prompt_parts()
        performer_input = performer_parts.get("system", "") + "\n\n===== USER =====\n" + performer_parts.get("user", "")
        # Performer的输出就是npc_output
        performer_output = npc_output

        # 应用Director输出的STATE_UPDATE（轴值、动量变化）
        self.director.apply_state_update()

        # 调试：打印轴值变化
        print(f"[DEBUG] axes after update: {self.state.axes}")

        # 保存历史
        self.state.history.append({"user": user_input, "npc": npc_output, "round": round_num})
        if len(self.state.history) > 10:
            self.state.history = self.state.history[-10:]

        # 清理
        self.event_pool.cleanup_low_priority(round_num)

        # 调试：写入临时文件
        final_model = get_current_model()
        log_to_file(f"[debug_result] 保存performer_model={final_model}")
        debug_result = {
            "round": round_num,
            "user": user_input,
            "npc": npc_output,
            "performer_model": final_model,  # 记录当前使用的模型
            # 各模块输入输出
            "perception_input": perception_input,
            "perception_output": perception_output,
            "predictor_input": predictor_input,
            "predictor_output": predictor_output,
            "director_input": director_input,
            "director_output": director_output,
            "performer_input": performer_input,
            "performer_output": performer_output,
        }

        # 写入调试文件
        try:
            debug_path = os.path.join(os.path.dirname(__file__), "..", "prototype", "logs", "debug", "engine_result.json")
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump(debug_result, f, ensure_ascii=False, indent=2)
            print(f"[Engine] 调试结果已写入: {debug_path}")
        except Exception as e:
            print(f"[Engine] 调试文件写入失败: {e}")

        timing['total'] = round(time.time() - t0, 2)
        
        print(f"[Engine] timing详情: {timing}")

        return {
            "round": round_num,
            "user": user_input,
            "npc": npc_output,
            "timing": timing,
            # 各模块输入输出
            "perception_input": perception_input,
            "perception_output": perception_output,
            "predictor_input": predictor_input,
            "predictor_output": predictor_output,
            "director_input": director_input,
            "director_output": director_output,
            "performer_input": performer_input,
            "performer_output": performer_output,
            # 各模块LLM原始输出（用于调试显示）
            "perception_raw_output": self.perception.get_last_llm_output() if hasattr(self, 'perception') else "",
            "predictor_raw_output": self.predictor.get_last_llm_output() if hasattr(self, 'predictor') else "",
            "director_raw_output": self.director.get_last_llm_output() if hasattr(self, 'director') else "",
            "performer_raw_output": self.performer.get_last_llm_output() if hasattr(self, 'performer') else "",
            # 状态
            "perception": asdict(perception),
            "story_patch": director_output,
            "neh_triggered": asdict(triggered) if triggered else None,
            "axes": self.state.axes.copy(),
            "momentum": self.state.momentum.copy(),
            "performer_model": get_current_model()
        }

    def save_state(self, filepath: str = None) -> str:
        """保存状态到文件"""
        return self.state.save(filepath)

    def get_state(self) -> dict:
        """获取当前状态"""
        return self.state.get_state()

    def save(self, filepath: str = None) -> str:
        return self.state.save(filepath)

    def load(self, filepath: str = None) -> bool:
        return self.state.load(filepath)

# ==================== API 接口 ====================
def create_engine() -> Engine:
    """创建引擎实例"""
    return Engine()

def start_engine(engine: Engine, npc_name: str, profile: str = "") -> dict:
    """启动引擎"""
    return engine.start(npc_name, profile)

def chat(engine: Engine, user_input: str, conversation_history: list = None) -> dict:
    """对话
    Args:
        engine: 引擎实例
        user_input: 用户输入
        conversation_history: 对话历史列表
    """
    return engine.run_turn(user_input, conversation_history)

def get_state(engine: Engine) -> dict:
    """获取状态"""
    return engine.get_state()

def save_state(engine: Engine, filepath: str = None) -> str:
    """保存状态"""
    return engine.save_state(filepath)

# ==================== 主程序 ====================
if __name__ == "__main__":
    if not API_KEY:
        print("请先在config.json设置API_KEY")
    else:
        engine = Engine()
        engine.start("沈予曦")

        test_inputs = ["你好", "你在做什么？", "我可以坐下吗？"]
        for inp in test_inputs:
            engine.run_turn(inp)

        print(f"\n最终轴值: {engine.state.axes}")
