# -*- coding: utf-8 -*-
"""
各角色输入输出的 JSON Schema 定义
使用 dataclass 定义类型安全的结构
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ==================== Director Schema ====================
@dataclass
class DirectorInput:
    """Director 输入结构"""
    user_input: str
    axes: Dict[str, int]  # 六轴状态
    history: List[Dict]   # 对话历史


@dataclass
class DirectorOutput:
    """Director 输出结构"""
    beat: str            # STALL/HOLD/EVOLVE/PIVOT
    axis_changes: Dict[str, int]  # {"Intimacy": 1, "Risk": -1}
    reasoning: str


# ==================== Predictor Schema ====================
@dataclass
class Event:
    """事件卡结构"""
    event_id: str
    archetype: str
    title: str
    trigger: str
    plot_hook: str


@dataclass
class PredictorOutput:
    """Predictor 输出结构"""
    events: List[Event]


# ==================== Performer Schema ====================
@dataclass
class Dialogue:
    """对话结构"""
    reaction: str
    evolution: str
    hook: str


@dataclass
class PerformerOutput:
    """Performer 输出结构"""
    scene: str
    dialogue: Dialogue
    emotion: str


# ==================== Observer Schema ====================
@dataclass
class Scores:
    """评分结构"""
    emotion_curve: float
    suspense: float
    memory: float
    immersion: float


@dataclass
class ObserverOutput:
    """Observer 输出结构"""
    scores: Scores
    summary: str


# ==================== 兼容旧版的 Dict Schema ====================
# 使用 dict 格式的 schema（兼容旧代码）

DIRECTOR_INPUT_SCHEMA = {
    "user_input": "string",
    "axes": "dict",
    "history": "list"
}

DIRECTOR_OUTPUT_SCHEMA = {
    "beat": "string",
    "axis_changes": "dict",
    "reasoning": "string"
}

PREDICTOR_OUTPUT_SCHEMA = {
    "events": [
        {
            "event_id": "string",
            "archetype": "string",
            "title": "string",
            "trigger": "string",
            "plot_hook": "string"
        }
    ]
}

PERFORMER_OUTPUT_SCHEMA = {
    "scene": "string",
    "dialogue": {
        "reaction": "string",
        "evolution": "string",
        "hook": "string"
    },
    "emotion": "string"
}

OBSERVER_OUTPUT_SCHEMA = {
    "scores": {
        "emotion_curve": "float",
        "suspense": "float",
        "memory": "float",
        "immersion": "float"
    },
    "summary": "string"
}


# ==================== Schema 验证函数 ====================
def validate_director_output(data: Dict) -> Optional[DirectorOutput]:
    """验证并解析 Director 输出"""
    try:
        if isinstance(data, dict):
            return DirectorOutput(
                beat=data.get("beat", "HOLD"),
                axis_changes=data.get("axis_changes", {}),
                reasoning=data.get("reasoning", "")
            )
    except Exception:
        pass
    return None


def validate_predictor_output(data: Dict) -> Optional[PredictorOutput]:
    """验证并解析 Predictor 输出"""
    try:
        if isinstance(data, dict) and "events" in data:
            events = []
            for e in data.get("events", []):
                if isinstance(e, dict):
                    events.append(Event(
                        event_id=e.get("event_id", ""),
                        archetype=e.get("archetype", ""),
                        title=e.get("title", ""),
                        trigger=e.get("trigger", ""),
                        plot_hook=e.get("plot_hook", "")
                    ))
            return PredictorOutput(events=events)
    except Exception:
        pass
    return None


def validate_performer_output(data: Dict) -> Optional[PerformerOutput]:
    """验证并解析 Performer 输出"""
    try:
        if isinstance(data, dict):
            dialogue_data = data.get("dialogue", {})
            if isinstance(dialogue_data, dict):
                dialogue = Dialogue(
                    reaction=dialogue_data.get("reaction", ""),
                    evolution=dialogue_data.get("evolution", ""),
                    hook=dialogue_data.get("hook", "")
                )
            else:
                dialogue = Dialogue(reaction="", evolution="", hook="")
            
            return PerformerOutput(
                scene=data.get("scene", ""),
                dialogue=dialogue,
                emotion=data.get("emotion", "")
            )
    except Exception:
        pass
    return None


def validate_observer_output(data: Dict) -> Optional[ObserverOutput]:
    """验证并解析 Observer 输出"""
    try:
        if isinstance(data, dict):
            scores_data = data.get("scores", {})
            if isinstance(scores_data, dict):
                scores = Scores(
                    emotion_curve=float(scores_data.get("emotion_curve", 0.0)),
                    suspense=float(scores_data.get("suspense", 0.0)),
                    memory=float(scores_data.get("memory", 0.0)),
                    immersion=float(scores_data.get("immersion", 0.0))
                )
            else:
                scores = Scores(0.0, 0.0, 0.0, 0.0)
            
            return ObserverOutput(
                scores=scores,
                summary=data.get("summary", "")
            )
    except Exception:
        pass
    return None
