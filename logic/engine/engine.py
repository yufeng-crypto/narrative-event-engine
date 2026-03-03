# -*- coding: utf-8 -*-
import sys
import io
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# 修复编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==================== 配置 ====================
class Config:
    ROLES_DIR = "logic/roles"
    STATE_FILE = "logic/engine/state.json"
    LOG_FILE = "logic/engine/log.json"
    
    DEFAULT_AXES = {
        "Intimacy": 2,
        "Risk": 3,
        "Info": 4,
        "Action": 5,
        "Rel": 1,
        "Growth": 7
    }

# ==================== 工具函数 ====================
def read_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return ""

def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def load_json(path: str) -> Dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_json(path: str, data: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== 状态管理 ====================
class StateManager:
    def __init__(self):
        self.state = {
            "axes": Config.DEFAULT_AXES.copy(),
            "momentum": {k: 0 for k in Config.DEFAULT_AXES},
            "round": 0,
            "locked_axes": [],
            "pending_events": [],
            "history": [],
            "npc": "沈予曦"
        }
        self._load()
    
    def _load(self):
        data = load_json(Config.STATE_FILE)
        if data:
            self.state.update(data)
    
    def save(self):
        save_json(Config.STATE_FILE, self.state)
    
    def get_axes(self) -> Dict[str, int]:
        return self.state["axes"].copy()
    
    def update_axes(self, changes: Dict[str, int]):
        for axis, delta in changes.items():
            if axis in self.state["locked_axes"]:
                continue
            current = self.state["axes"].get(axis, 0)
            new_val = max(0, min(10, current + delta))
            self.state["axes"][axis] = new_val
            if new_val >= 10:
                if axis not in self.state["locked_axes"]:
                    self.state["locked_axes"].append(axis)
    
    def add_history(self, entry: Dict):
        self.state["round"] += 1
        entry["round"] = self.state["round"]
        self.state["history"].append(entry)
    
    def get_context(self, max_rounds: int = 5) -> str:
        recent = self.state["history"][-max_rounds:] if self.state["history"] else []
        ctx = f"Current axes:\n{json.dumps(self.state['axes'], ensure_ascii=False)}\n\nRecent {max_rounds} rounds:"
        for h in recent:
            ctx += f"\n- Round {h.get('round', '?')}: {h.get('user_input', '?')[:50]}"
        return ctx

# ==================== 角色模块 ====================
class Director:
    """导演层 - 决策节拍和轴向"""
    
    def __init__(self, state: StateManager):
        self.state = state
        self.prompt_template = read_file(f"{Config.ROLES_DIR}/director.md")
    
    def process(self, user_input: str, npc_output: str = "") -> Dict:
        context = self.state.get_context()
        
        # 实际应用中这里调用LLM
        # 只返回决策结果
        return self._mock_decision(user_input)
    
    def _mock_decision(self, user_input: str) -> Dict:
        length = len(user_input)
        
        if length < 5:
            return {"beat": "HOLD", "axis_changes": {}, "reasoning": "Input too short"}
        elif "battle" in user_input or "PK" in user_input:
            return {"beat": "EVOLVE", "axis_changes": {"Action": 1, "Risk": 1}, "reasoning": "User proposes battle"}
        elif "刷" in user_input or "火箭" in user_input:
            return {"beat": "EVOLVE", "axis_changes": {"Intimacy": 1}, "reasoning": "User sends gift"}
        else:
            return {"beat": "HOLD", "axis_changes": {"Intimacy": 1}, "reasoning": "Normal interaction"}


class Predictor:
    """预测层 - 生成事件卡"""
    
    def __init__(self, state: StateManager):
        self.state = state
        self.prompt_template = read_file(f"{Config.ROLES_DIR}/predictor.md")
    
    def process(self, director_decision: Dict, user_input: str) -> List[Dict]:
        return self._mock_events(director_decision)
    
    def _mock_events(self, decision: Dict) -> List[Dict]:
        beat = decision.get("beat", "HOLD")
        
        if beat == "EVOLVE":
            return [
                {
                    "event_id": "TEST_EVENT_01",
                    "archetype": "ARC_W_01",
                    "title": "Test Event",
                    "trigger": {"axis": "Action", "value": ">5"},
                    "choices": [
                        {"label": "A", "impact": {"Intimacy": 1}},
                        {"label": "B", "impact": {"Risk": 1}}
                    ]
                }
            ]
        return []


class Performer:
    """表现层 - 生成NPC对话"""
    
    def __init__(self, state: StateManager):
        self.state = state
        self.prompt_template = read_file(f"{Config.ROLES_DIR}/performer.md")
        self.npc_template = read_file(f"{Config.ROLES_DIR}/npc_shenyuxi.md")
    
    def process(self, director_decision: Dict, events: List[Dict], user_input: str) -> str:
        return self._mock_performer(user_input, director_decision)
    
    def _mock_performer(self, user_input: str, decision: Dict) -> str:
        if "battle" in user_input:
            return "笑死，本小姐直播以来就没输过！"
        elif "火箭" in user_input:
            return "3000？对本小姐来说算正常水平啦~"
        elif "奶茶" in user_input:
            return "好吧...勉强让你请一次~"
        else:
            return "......你到底想怎样？"


class Observer:
    """观察层 - 纯旁观者评估"""
    
    def __init__(self, state: StateManager):
        self.state = state
    
    def process(self, user_input: str, npc_output: str, director_decision: Dict) -> Dict:
        return {
            "emotion_curve": self._eval_emotion_curve(user_input, npc_output),
            "suspense": self._eval_suspense(user_input),
            "character_memory": self._eval_memory(user_input),
            "immersion": self._eval_immersion(user_input, npc_output)
        }
    
    def _eval_emotion_curve(self, user: str, npc: str) -> int:
        emotional_words = ["哭", "笑", "生气", "开心", "难过", "委屈", "甜"]
        score = 3
        for w in emotional_words:
            if w in user or w in npc:
                score += 1
        return min(5, score)
    
    def _eval_suspense(self, user: str) -> int:
        question_marks = user.count("?")
        if question_marks > 2:
            return 5
        elif question_marks > 0:
            return 3
        return 2
    
    def _eval_memory(self, user: str) -> int:
        return 4
    
    def _eval_immersion(self, user: str, npc: str) -> int:
        length = len(user) + len(npc)
        if length > 50:
            return 5
        elif length > 20:
            return 4
        return 3


# ==================== 引擎核心 ====================
class Engine:
    """叙事引擎主程序"""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.director = Director(self.state_manager)
        self.predictor = Predictor(self.state_manager)
        self.performer = Performer(self.state_manager)
        self.observer = Observer(self.state_manager)
        
        print("[Engine] aibaji Engine initialized")
        print(f"[Engine] Current NPC: {self.state_manager.state['npc']}")
    
    def run(self, user_input: str) -> Dict:
        print(f"\n{'='*50}")
        print(f"[Input] {user_input[:50]}...")
        
        # Step 1: Director
        director_result = self.director.process(
            user_input, 
            self.state_manager.state.get("last_npc_output", "")
        )
        print(f"[Director] {director_result['beat']} - {director_result['reasoning']}")
        
        # Step 2: Predictor
        events = self.predictor.process(director_result, user_input)
        print(f"[Predictor] Generated {len(events)} events")
        
        # Step 3: Performer
        npc_output = self.performer.process(director_result, events, user_input)
        print(f"[Performer] {npc_output}")
        
        # Step 4: Observer
        observer_result = self.observer.process(user_input, npc_output, director_result)
        print(f"[Observer] emotion={observer_result['emotion_curve']}/suspense={observer_result['suspense']}/immersion={observer_result['immersion']}")
        
        # Step 5: Update state
        self.state_manager.update_axes(director_result.get("axis_changes", {}))
        self.state_manager.add_history({
            "user_input": user_input,
            "npc_output": npc_output,
            "director": director_result,
            "events": events,
            "observer": observer_result
        })
        self.state_manager.state["last_npc_output"] = npc_output
        self.state_manager.save()
        
        return {
            "npc_output": npc_output,
            "director": director_result,
            "events": events,
            "observer": observer_result,
            "axes": self.state_manager.get_axes()
        }


# ==================== 主程序 ====================
if __name__ == "__main__":
    engine = Engine()
    
    test_inputs = [
        "我给你刷个火箭",
        "3000才能喝奶茶啊",
        "我们battle吧",
        "好了不闹了，去喝奶茶吧"
    ]
    
    for user_input in test_inputs:
        result = engine.run(user_input)
        print(f"\n[NPC] {result['npc_output']}")
        print(f"[Axes] {result['axes']}")
