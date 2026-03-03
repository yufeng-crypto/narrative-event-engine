# aibaji引擎 - 核心逻辑协议 (ENGINE_CORE)

> 版本：3.0 | 生效日期：2026-02-27

---

## 一、引擎核心定位

本互动叙事双引擎架构为对话式 AI 角色设计，核心是通过"微观张力引擎 + 宏观 NEH 叙事视界系统"，实现从日常互动拉扯到不可逆剧情质变的全链路体验。

### 双引擎核心分工

| 引擎 | 职责 | 周期 |
|------|------|------|
| **微观张力引擎** | 日常对话，体验拉扯 | 每轮 |
| **宏观 NEH 系统** | 剧情量变到质变 | 每5-10轮 |

### v3.1 版本优化

**并行执行优化**：
- NEH-Predictor（每5轮）与 NEH-Trigger 检查并行执行
- 减少等待时间，提升响应速度

**Prompt 格式优化**：
- MD 模板文件（角色设定+规则+格式要求）放在 **system prompt**
- 参数（六轴、历史、用户输入等）放在 **user prompt**
- 便于调试显示，清晰区分系统指令和输入参数

**Director 输出处理优化**：
- Director LLM 返回包含两部分：STORY_PATCH（叙事指令）和 STATE_UPDATE_JSON（状态更新）
- 程序通过 `===STORY_PATCH_BEGIN===` 和 `===STORY_PATCH_END===` 标记提取 STORY_PATCH
- STORY_PATCH 传递给 Performer 作为输入
- STATE_UPDATE_JSON 解析后更新到角色 state（六轴、动量、线程等）

---

## 二、全局状态管理

### 2.1 Session State Manager（会话状态管理器）

**核心定位**：唯一状态枢纽，所有动态数据的读写入口

**存储内容**：
- 6大叙事体验轴当前数值（0-10整数）
- 各轴动量值（Momentum，-2到+2整数）
- 线程池（最多8条）
- NEH-EventPool（未触发事件卡，最多10张）
- 当前交互轮次计数
- 用户近3轮主动性均值

**读写权限**：
- 只读：感知层、导演层、表现层、NEH-Predictor、NEH-Trigger
- 写入：仅叙事导演层

---

## 三、六大叙事体验轴

| 轴向 | 名称 | 0-2 | 3-7 | 8-10 |
|------|------|-----|-----|------|
| Intimacy | 亲密 | 社交面具 | 暧昧/拉扯 | 偏爱/灵魂契约 |
| Risk | 风险 | 安全 | 焦虑/暴露 | 致命威胁 |
| Information | 信息 | 透明 | 碎片线索 | 核心秘密 |
| Action | 行动 | 静态 | 位移/目标 | 环境剧变 |
| Relationship | 关系 | 陌生 | 契约建立 | 灵魂纠缠 |
| Growth | 成长 | 起点 | 信仰微调 | 价值观重塑 |

### 核心通用规则

1. **封顶限制**：单轴默认上限8分
2. **互锁限制**：亲密轴严禁超过关系轴+2
3. **10分破局条件**：需同时满足主动性=3、L2场景、地基轴达标

---

## 四、微观张力引擎全模块

### 4.1 初始化专家（Initializer PRO Plus V2.3）

**核心使命**：冷启动，将静态人设转化为动态叙事第一帧

**场景合成三要素**：
- 中段切入
- 五感锚点
- 脆弱性瞬间

**输出**：
- 150字内场景档案（含入场原因、五感环境、脆弱点）
- 初始轴数值
- 初始线程池JSON
- 首轮STORY_PATCH表演指令

### 4.2 感知层（Narrative Perception Analyst v2.1）

**核心使命**：解析用户输入，输出结构化感知简报

**四大核心信号**：

#### 主动性（0-3）
| 评分 | 等级 | 行为表现 |
|------|------|----------|
| 0 | 敷衍 | "哦"、"……"，触发强制压力累积 |
| 1 | 常规 | 被动回应、简短观望 |
| 2 | 主动 | 正常互动、有来有往 |
| 3 | 强驱动 | 长文本、复杂动作、深度演绎 |

#### 交互意图
| 标签 | 说明 |
|------|------|
| **Story** | 剧情推进 |
| **Chat** | 情感交流 |
| **Verify** | 核对事实/套话 |
| **Conflict** | 对抗挑衅 |

#### 情感调性
Warm / Teasing / Neutral / Pensive / Sad / Vulnerable / Fearful / Cold / Annoyed / Hostile

#### 停滞分（0-3）
| 评分 | 等级 | 说明 |
|------|------|------|
| 0 | 正常 | 叙事流畅 |
| 1 | 轻微重复 | 轻微停滞 |
| 2 | 警戒 | 死循环预警 |
| 3 | 枯竭 | 需L2场景救场 |

#### 权力重心
User-Led / NPC-Led / Balanced

### 4.3 叙事导演层（Narrative Director PRO）

**核心使命**：数值计算、节奏控场、生成STORY_PATCH、调用NEH-Trigger

**核心工作**：
1. 解析感知层信号
2. 按规则更新6轴数值 + 动量
3. 检查NEH触发
4. 生成标准化STORY_PATCH
5. 更新线程池

**动量机制**：
- 同向变化 +1（上限+2）
- 反向变化 -1（下限-2）
- 惯性加速 + 阻力缓冲

**线程管理**：
- 最多8条线程
- 支持操作：create / touch / pause / resolve
- 按优先级推进

**输出STORY_PATCH**：
- 叙事等级
- 焦点(focus)
- 潜台词
- 节拍计划
- 张力工具
- 钩子
- 禁止项

### 4.4 表现层（The Master Performer）

**核心使命**：将STORY_PATCH转化为沉浸式文学化对白

**核心规则**：
- 三段式节拍：反应拍→演进拍→钩子拍
- 五感建模（每轮至少2种感官细节）
- Show Don't Tell（动作外化情绪）

**演绎要求**：
- 张力工具具象化
- 对白保留潜台词
- 自然融入钩子
- 禁止代用户操作、跳脱时间线

**输出格式**：角色名 + 括号内动作神态描写 + 对白

**动作与对白比例**：≥6:4

---

## 五、核心规则

### 5.1 三段式节拍

每轮剧情必须包含：
1. **反应拍**：物理/生理反馈
2. **演进拍**：张力工具执行
3. **钩子拍**：悬念/问题抛出

### 5.2 优先级逻辑

| 优先级 | 类型 | 说明 |
|--------|------|------|
| P0 | 拒绝/不适 | 安全词、底线触碰 |
| P1 | 对账/纠错 | 事实核实、逻辑修正 |
| P2 | 停滞救场 | 防止尬聊 |
| P3 | 剧情指令 | 主动推剧情 |
| P4 | 情感响应 | 日常互动 |

### 5.3 停滞救场规则

- Stall ≥ 2：行动轴/信息轴 +1
- Stall = 3：允许L2场景

### 5.4 数值阻尼协议

#### 边界重力阻尼
当轴值≥8时，增量应用对数阻尼：
```
Δ_real = floor(Δ × (1 - (Current - 7) / 4))
```

#### 节奏斜率限制
- 单轮单轴Δ最大3
- 同一轴连续3轮正向增长，第4轮起增量衰减50%

#### 压力阀与阻尼对冲
- P ≥ 5.0时：移除所有阻尼

### 5.5 合规原则

- 高张力场景侧重文学化感官描写
- 避开露骨内容
- 动作与对白比例≥6:4

---

## 六、张力工具字典（6轴×3等级）

### Intimacy（亲密轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 社交安全距离、称谓固化、眼神公事化、礼貌性客气 |
| 3-7 | 拉扯期 | 微碰触、眼神躲闪、推拉回复、私人领地入侵 |
| 8-10 | 巅峰期 | 禁忌共鸣、逻辑断裂、脆弱点袒露、感官剥夺、主权烙印、宿命式交付、界限消融、静谧狂欢 |

### Risk（风险轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 逻辑自洽、常态维持、秩序确认、安全话题兜底 |
| 3-7 | 拉扯期 | 环境阴影、异样声响、逻辑裂痕、被监视感 |
| 8-10 | 巅峰期 | 物理环境崩溃、致命倒计时、强制二选一、不可逆伤损 |

### Information（信息轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 标准简报、官方回避、事实堆砌、假性配合 |
| 3-7 | 拉扯期 | 只说一半、隐晦线索、回避式反问、假性公开 |
| 8-10 | 巅峰期 | 话到嘴边改口、被打断的解释、高价真相、认知重构线索 |

### Relationship（关系轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 职业性尊重、边界声明、利益对等、身份标签 |
| 3-7 | 拉扯期 | 权力试探、轻微质疑、身份暗示、非正式契约 |
| 8-10 | 巅峰期 | 阵营对质、背叛契机、忠诚度测试、绝对臣服/对等 |

### Action（行动轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 静止坐姿、程序化位移、背景化互动、任务驱动 |
| 3-7 | 拉扯期 | 位置位移、目标引导、中途阻碍、转场暗示 |
| 8-10 | 巅峰期 | 场景强行切换、资源/体力耗尽、决定性打击、物理围困 |

### Growth（成长轴）
| 等级 | 阶段 | 工具/行为 |
|------|------|----------|
| 0-2 | 潜伏期 | 话术面具、舒适圈维持、公众形象锚定、拒绝内省 |
| 3-7 | 拉扯期 | 内心独白碎念、信仰微调、旧忆闪回、自我怀疑 |
| 8-10 | 巅峰期 | 核心信仰崩塌、性格面具破碎、决定性牺牲、身份彻底觉醒 |

---

## 七、NEH 叙事视界系统

### 7.1 四大核心组件

| 组件 | 定位 | 是否有独立Prompt |
|------|------|-----------------|
| NEH-Archetypes | 剧情母版库（静态模板） | ❌ 无 |
| NEH-Predictor | 事件卡生成器（编剧） | ✅ 有 |
| NEH-EventPool | 事件卡存储池 | ❌ 无 |
| NEH-Trigger | 事件触发器 | ❌ 无独立Prompt |

### 7.2 NEH母版库（32个）

#### Man vs World（5个）
| ID | 名称 | 叙事逻辑 |
|----|------|----------|
| ARC_W_01 | 不速之客 | 第三方竞争/敌意出现 |
| ARC_W_02 | 社交破裂 | 身份暴露引发骚乱 |
| ARC_W_03 | 紧急召唤 | 外部任务强行中断 |
| ARC_W_04 | 资源争夺 | 外部力量介入抢夺 |
| ARC_W_05 | 舆论风暴 | 行为被偷拍/直播 |

#### Man vs Environment（8个）
| ID | 名称 | 叙事逻辑 |
|----|------|----------|
| ARC_E_01 | 物理囚笼 | 断电/故障/暴雨被迫共处 |
| ARC_E_02 | 资产损毁 | 关键道具意外损毁 |
| ARC_E_03 | 场景崩塌 | 无法继续停留 |
| ARC_E_04 | 失物寻找 | 共同寻找才能离开 |
| ARC_E_05 | 感官侵蚀 | 嘈杂/安静环境缩短距离 |
| ARC_E_06 | 突发灾害 | 地震/暴雨等灾害迫使角色共同应对 |
| ARC_E_07 | 场地危机 | 场景安全受威胁（如停电/失火） |
| ARC_E_08 | 强制转移 | 角色被强制带离当前场景 |

#### Man vs Relationship（11个）
| ID | 名称 | 叙事逻辑 |
|----|------|----------|
| ARC_R_01 | 致命误会 | 无心动作被深度解读 |
| ARC_R_02 | 秘密外溢 | 弱点/黑历史被揭开 |
| ARC_R_03 | 旧识干预 | 前任/旧友信息介入 |
| ARC_R_04 | 信任余震 | 小谎言被当面拆穿 |
| ARC_R_05 | 依赖转移 | 突发虚弱产生病理性依赖 |
| ARC_R_06 | 情敌突袭 | 外部角色介入打断亲密互动 |
| ARC_R_07 | 工作干扰 | 职业角色/任务打断当前场景 |
| ARC_R_08 | 意外访客 | 突发访客打破独处氛围 |
| ARC_R_09 | 信息错位 | 双方掌握的关键信息不一致 |
| ARC_R_10 | 行为误解 | 用户动作被NPC错误解读 |
| ARC_R_11 | 第三方挑拨 | 他人故意传递错误信息 |

#### Man vs Self（8个）
| ID | 名称 | 叙事逻辑 |
|----|------|----------|
| ARC_S_01 | 梦想受挫 | 引以为傲的才华遭否定 |
| ARC_S_02 | 终极二选一 | 理想vs好感抉择 |
| ARC_S_03 | 面具剥落 | 职业身份彻底崩坏 |
| ARC_S_04 | 价值背离 | 违背核心信念导致坍缩 |
| ARC_S_05 | 余烬重塑 | 告别旧自我开启新阶段 |
| ARC_S_06 | 利益冲突 | NPC面临情感/利益二选一 |
| ARC_S_07 | 情感抉择 | NPC在多个角色间选择 |
| ARC_S_08 | 成长抉择 | NPC需突破舒适圈完成成长 |

### 7.3 NEH-Predictor完整Prompt

**Role**: NEH 叙事预测器 (NEH-Predictor v1.0)

**核心使命**：根据当前全局状态，从NEH母版库匹配适配模板，生成标准化NEH事件卡

**输入数据**：
- 当前6轴数值：{Current_Axes}
- 当前线程池状态：{Current_Threads}
- 用户近3轮主动性均值：{Avg_Initiative}

**输出格式**：
```json
{
  "event_id": "neh_xxxxxxxx",
  "archetype": "母版名称",
  "trigger_condition": {"Intimacy": "≥x", "Risk": "≥x", ...},
  "impact": {
    "axes_change": {"Intimacy": Δx, ...},
    "threads_operation": [{"id": "txx", "operation": "create/touch/pause/resolve", "new_label": "..."}]
  },
  "priority": 1/2/3,
  "description": "50字内事件描述"
}
```

### 7.4 NEH-EventPool管理规则

**容量**：最多10张事件卡

**淘汰规则**：
- 触发的事件卡立即移除
- 低优先级（3级）未触发事件每10轮清理1次
- 容量满时，优先移除最旧的低优先级事件

**Python实现**：
```python
class NEHEventPool:
    def __init__(self, max_size=10):
        self.events = []
        self.max_size = max_size
    
    def add(self, event):
        if len(self.events) >= self.max_size:
            # 移除最旧的低优先级事件
            low_priority = [e for e in self.events if e.get('priority') == 3]
            if low_priority:
                self.events.remove(min(low_priority, key=lambda x: x.get('created_at', 0)))
            else:
                self.events.pop(0)
        self.events.append(event)
    
    def remove_triggered(self, event_id):
        self.events = [e for e in self.events if e.get('event_id') != event_id]
    
    def cleanup_low_priority(self, current_round):
        if current_round % 10 == 0:
            self.events = [e for e in self.events if e.get('priority') != 3]
```

### 7.5 NEH-Trigger触发逻辑

**触发条件**：导演层每轮数值计算后

**判定逻辑**：
```python
def check_trigger(event_pool, current_axes, user_initiative):
    triggered = None
    for event in event_pool.events:
        if evaluate_condition(event['trigger_condition'], current_axes, user_initiative):
            if triggered is None or event['priority'] < triggered['priority']:
                triggered = event
    return triggered

def evaluate_condition(condition, axes, initiative):
    for axis, op_value in condition.items():
        if axis == 'initiative':
            current = initiative
        else:
            current = axes.get(axis, 0)
        
        op, value = op_value.replace('≥', ''), int(op_value.replace('≥', ''))
        if op == '≥' and current < value:
            return False
    return True
```

### 7.6 NEH铁律

**触发的大事件不可逆转**，数值变化与剧情走向无回撤可能。

---

## 八、主链路数据流向

```
用户输入
    ↓
【感知层】→ 感知简报
    ↓
【导演层】→ 数值计算 + NEH-Trigger → STORY_PATCH + 状态包
    ↓
【表现层】→ 沉浸式对白
    ↓
用户回应 → 循环
```

### NEH子系统嵌入

```
每5-10轮 → NEH-Predictor生成事件卡 → 存入EventPool
每轮 → NEH-Trigger扫描EventPool → 满足条件触发 → 执行impact
```

---

## 九、配置文件

| 参数 | 值 | 说明 |
|------|------|------|
| Unmasked_Filter | true | 启用绝对真实模式 |
| NEH_Interval | 5-10 | 候选卡生成间隔(轮) |
| Pressure_Threshold | 5.0 | 压力触发阈值 |
| Max_Axis_Value | 8 | 单轴默认上限 |
| Max_Threads | 8 | 最大线程数 |
| Max_Events | 10 | 事件池容量 |
| Action_Dialogue_Ratio | 0.6 | 动作对白比例≥6:4 |

---

## 十、Director 输出处理流程

### 10.1 LLM 返回格式

Director LLM 返回的内容包含两部分，用标记分隔：

**第一部分：STORY_PATCH**（叙事指令）
```
===STORY_PATCH_BEGIN===
[STORY_PATCH]
- pacing_constraint: ...
- focus: ...
- logic_subtext: ...
- patch_mode: ...
- continuity_requirement: true/false
- beat_plan: ...
- tension_tools: ...
- hook: ...
- hard_avoid: ...
===STORY_PATCH_END===
```

**第二部分：STATE_UPDATE_JSON**（状态更新）
```json
{
  "driving_signals": {...},
  "axes_next": {...},
  "momentum_next": {...},
  "open_threads_next": [...],
  "meta": {...}
}
```

### 10.2 程序解析流程

1. **提取 STORY_PATCH**
   - 使用正则表达式提取 `===STORY_PATCH_BEGIN===` 和 `===STORY_PATCH_END===` 之间的内容
   - 解析各字段（focus, logic_subtext, patch_mode, beat_plan, tension_tools, hook 等）
   - 封装为 StoryPatch 对象

2. **提取 STATE_UPDATE_JSON**
   - 使用正则表达式提取 `===STATE_UPDATE_JSON===` 和 `===STATE_UPDATE_END===` 之间的内容
   - 解析 JSON 获取 axes_next, momentum_next, open_threads_next 等

3. **传递给 Performer**
   - STORY_PATCH 内容作为 Performer 的 user prompt 的一部分
   - 让 Performer 知道本轮的叙事指令

4. **更新 State**
   - 应用 STATE_UPDATE_JSON 到角色状态
   - axes_next: 更新六轴绝对值
   - momentum_next: 更新动量值
   - open_threads_next: 更新线程池

### 10.3 调试显示

GUI 的 Director 输入/输出窗口显示：
- **输入**: system prompt (MD模板) + user prompt (参数)
- **输出**: 解析后的 STORY_PATCH 和 STATE_UPDATE_JSON

---

*本协议为aibaji引擎最高指令集，所有叙事演算必须遵循此协议*

*版本：3.0 | 更新日期：2026-02-27*
