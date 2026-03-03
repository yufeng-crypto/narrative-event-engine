# 爱巴基斯坦叙事引擎 (aibaji Engine) 系统架构文档

## 1. 概述

爱巴基斯坦叙事引擎是一个模块化的 NPC 对话生成系统，通过多层角色分工实现复杂场景下的自然对话交互。

### 核心特性
- **模块化设计**：Director、Predictor、Performer、Observer 四层分离
- **状态驱动**：六轴状态机追踪对话进程
- **LLM 驱动**：所有角色决策由 MiniMax API 生成

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Engine (引擎核心)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Director   │─▶│  Predictor  │─▶│  Performer   │      │
│  │   (导演层)    │  │   (预测层)   │  │   (表现层)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                                      │            │
│         └──────────────▶  Observer ◀──────────┘            │
│                      (观察层)                                │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   StateManager (状态管理)                    │
│  - 六轴状态: Intimacy/Risk/Info/Action/Rel/Growth          │
│  - 对话历史                                                │
│  - 轴向锁定/事件队列                                        │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    MiniMax API (LLM)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 各模块职责

### 3.1 Director (导演层)
**职责**：判定叙事节拍，计算轴向变化

**节拍类型**：
- `STALL` - 停滞/等待
- `HOLD` - 保持现状
- `EVOLVE` - 演进/变化
- `PIVOT` - 转折/突变

**输出**：
```json
{
  "beat": "EVOLVE",
  "axis_changes": {"Intimacy": 1, "Action": 1},
  "reasoning": "用户送礼物，亲密度增加"
}
```

### 3.2 Predictor (预测层)
**职责**：生成候选事件卡

**输出**：
```json
{
  "events": [{
    "event_id": "EVT_001",
    "archetype": "母版类型",
    "title": "事件名称",
    "trigger": "触发条件",
    "plot_hook": "场景钩子"
  }]
}
```

### 3.3 Performer (表现层)
**职责**：生成 NPC 对话

**输出**：
```json
{
  "scene": "场景描述",
  "dialogue": {
    "reaction": "反应",
    "evolution": "演进",
    "hook": "钩子"
  },
  "emotion": "情感状态"
}
```

### 3.4 Observer (观察层)
**职责**：评估剧情质量

**输出**：
```json
{
  "scores": {
    "emotion_curve": 7.5,
    "suspense": 4.5,
    "memory": 6.5,
    "immersion": 8.0
  },
  "summary": "评估总结"
}
```

---

## 4. 六轴状态系统

| 轴名 | 含义 | 范围 |
|------|------|------|
| Intimacy | 亲密度 | 0-10 |
| Risk | 风险值 | 0-10 |
| Info | 信息量 | 0-10 |
| Action | 行动力 | 0-10 |
| Rel | 关系值 | 0-10 |
| Growth | 成长度 | 0-10 |

**状态规则**：
- 轴值达到 10 时自动锁定
- 每轮对话由 Director 计算轴向变化
- 状态持久化到 `state.json`

---

## 5. API 调用策略

### 5.1 MiniMax API 配置
```json
{
  "api_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
  "model": "MiniMax-M2.5",
  "temperature": 0.7
}
```

### 5.2 关键工程要点

⚠️ **重要：MiniMax API 不支持多个 system 消息**

必须将多个 system 消息合并为一个：

```python
def merge_system_messages(messages):
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
```

### 5.3 重试机制
- 超时时间：60 秒
- 重试次数：3 次
- 指数退避：2^n 秒

---

## 6. 文件结构

```
logic/
├── engine/
│   ├── engine.py          # 简化版引擎（mock）
│   ├── engine_llm.py      # 完整版 LLM 引擎
│   ├── config.json        # API 配置
│   └── state.json         # 状态持久化
├── roles/
│   ├── director.md        # 导演角色定义
│   ├── predictor.md       # 预测角色定义
│   ├── performer.md       # 表演角色定义
│   ├── observer.md        # 观察角色定义
│   ├── npc_shenyuxi.md    # NPC 沈予曦设定
│   └── ...
└── ...
```

---

## 7. 对话流程示例

```
用户: "我到了约定的餐厅，给你打电话了，你在哪？"

↓

【Director】
输入: 六轴状态 + 对话历史 + NPC角色 + 用户输入
输出: {"beat": "HOLD", "axis_changes": {"Info": "+1", "Rel": "+1"}, ...}

【Predictor】
输入: Director决策 + 六轴 + 历史
输出: {"events": [{"title": "迟到的解释", ...}]}

【Performer】
输入: NPC设定 + Director + Predictor + 六轴 + 历史
输出: {"dialogue": {"reaction": "抱歉让你等了！..."}}

【Observer】
输入: 历史 + 用户输入 + NPC回复
输出: {"scores": {"emotion_curve": 7.5, ...}}

↓

NPC: "抱歉让你等了！我刚刚处理完工作上的事，现在正在赶过来的路上..."
```

---

## 8. 后续优化方向

1. **流式输出**：支持实时逐字显示
2. **多 NPC 支持**：扩展到多个 NPC 同时对话
3. **记忆系统**：长期记忆与短期记忆分离
4. **事件分支**：支持多选项分支剧情
5. **语音合成**：接入 TTS 实现语音对话

---

*文档版本: 1.0*  
*更新时间: 2026-02-26*
