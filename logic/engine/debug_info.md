# 调试信息展示

## 场景：用户到达餐厅，给沈予曦打电话

当前六轴：{"Intimacy": 10, "Rel": 10, "Action": 8, "Risk": 5, "Info": 9, "Growth": 9}

---

### Director

**收到的messages（实际传递给LLM的内容）：**

```
[0] role=system
    content: 你是Director。根据六轴和用户输入，输出JSON：
           {"beat": "STALL|HOLD|EVOLVE|PIVOT", "axis_changes": {}, "reasoning": ""}

[1] role=system  
    content: 当前六轴: {"Intimacy": 10, "Rel": 10, "Action": 8, "Risk": 5, "Info": 9, "Growth": 9}

[2] role=system
    content: 对话历史: （从上次结束继续：直播间→私信→battle→约会确定）

[3] role=system
    content: NPC角色设定: 沈予曦，24岁，傲娇千金主播，渴望被真正看见

[4] role=user
    content: 用户说: 我到了约定的餐厅，拨通了沈予曦的电话
           请输出JSON决策
```

**期望输出（LLM应返回）：**
```json
{"beat": "HOLD", "axis_changes": {"Action": 1}, "reasoning": "约会场景，行动升级"}
```

---

### Predictor

**收到的messages：**

```
[0] role=system
    content: 你是Predictor。根据决策生成事件卡

[1] role=system
    content: 六轴: {"Intimacy": 10, "Rel": 10, "Action": 8}

[2] role=system
    content: Director决策: {"beat": "HOLD", "axis_changes": {"Action": 1}}

[3] role=user
    content: 用户: 我到了约定的餐厅，拨通了沈予曦的电话
           请生成事件卡
```

**期望输出：**
```json
{"events": [{"event_id": "DATE_01", "title": "餐厅见面", "hook": "沈予曦接电话"}]}
```

---

### Performer

**收到的messages：**

```
[0] role=system
    content: 你是Performer。生成NPC对话

[1] role=system
    content: 六轴: {"Intimacy": 10, "Rel": 10, "Action": 8}

[2] role=system
    content: Director决策: {"beat": "HOLD", "axis_changes": {"Action": 1}}

[3] role=system
    content: 事件: {"events": [...]}

[4] role=system
    content: NPC设定: 沈予曦，24岁傲娇千金，内心孤独渴望被看见

[5] role=user
    content: 用户: 我到了约定的餐厅，拨通了沈予曦的电话
           请生成NPC对话
```

**期望输出：**
```json
{
  "scene": "星光餐厅VIP包间，手机铃声响起",
  "dialogue": {
    "reaction": "（看到来电，稍微紧张）喂？",
    "evolution": "你...你到了？本小姐马上就到...",
    "hook": "你不许先走！"
  },
  "emotion": "Teasing"
}
```

---

### Observer

**收到的messages：**

```
[0] role=system
    content: 你是Observer。纯旁观者评估

[1] role=system
    content: 历史: 直播间→battle→私信→约会确定

[2] role=user
    content: 用户: 我到了餐厅打电话
    NPC: （餐厅场景对话）
    请评估
```

**期望输出：**
```json
{"scores": {"emotion_curve": 4, "suspense": 4, "memory": 5, "immersion": 5}, "summary": "线下见面场景转换成功"}
```
