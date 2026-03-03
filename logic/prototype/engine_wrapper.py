# -*- coding: utf-8 -*-
"""
引擎对接层 - main.py 调用此模块来使用叙事引擎
"""

import sys
import os

# 添加 engine 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from engine_llm import Engine, create_engine, start_engine, chat, get_state, save_state

# ==================== 对话管理器 ====================
class DialogueManager:
    """对话管理器 - 封装引擎调用"""
    
    def __init__(self):
        self.engine = None
        self.current_npc = None
    
    def start_dialogue(self, npc_id: str, character_profile: str = "") -> dict:
        """开始对话"""
        self.engine = create_engine()
        result = start_engine(self.engine, npc_id, character_profile)
        self.current_npc = npc_id
        return result
    
    def send_message(self, user_input: str) -> dict:
        """发送消息"""
        if not self.engine:
            return {"error": "请先开始对话"}
        return chat(self.engine, user_input)
    
    def get_status(self) -> dict:
        """获取状态"""
        if not self.engine:
            return {"error": "未启动"}
        return get_state(self.engine)

# ==================== 便捷函数 ====================
_manager = None

def init(npc_id: str, profile: str = "") -> dict:
    """初始化对话"""
    global _manager
    _manager = DialogueManager()
    return _manager.start_dialogue(npc_id, profile)

def say(message: str) -> dict:
    """发送消息"""
    global _manager
    if not _manager:
        return {"error": "请先调用 init() 初始化"}
    return _manager.send_message(message)

def status() -> dict:
    """获取状态"""
    global _manager
    if not _manager:
        return {"error": "未启动"}
    return _manager.get_status()

# ==================== 测试 ====================
if __name__ == "__main__":
    import json
    
    print("测试引擎对接...")
    
    # 测试初始化
    result = init("沈予曦")
    print(f"初始化: {json.dumps(result, ensure_ascii=False)[:200]}...")
    
    # 测试对话
    result = say("你好")
    print(f"回复: {result.get('npc', '')[:100]}...")
    
    # 状态
    st = status()
    print(f"轴值: {st.get('axes', {})}")
