# 叙事引擎模块定义（人类阅读版）

> 本文档根据 2026-03-05 实际运行的程序代码编写

---

## 系统架构

### 整体架构
```
┌─────────────────────────────────────────────────────────────┐
│              NPC Chat Prototype (main.py)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   GUI 层 (tkinter)                   │   │
│  │  - 角色选择    - 对话窗口    - 输入框             │   │
│  │  - 六轴显示    - 事件卡显示  - 调试标签页        │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
                    engine_llm.py
```

### GUI 界面布局
- **左侧**：聊天窗口（显示对话）+ 输入框
- **右侧**：六轴面板 + 事件卡面板
- **下方**：调试标签页（Perception / Director / Predictor / Performer / Performer Direct）

---

## 模块列表

1. Initializer（初始化）
2. PerceptionLayer（感知层）
3. DirectorLayer（导演层）
4. PerformerLayer（表演层）
5. NEHPredictor（事件预测）
6. NEHEventPool（事件池）
7. ObserverLayer（观察层）

---

## 1. Initializer（初始化模块）

### 引擎处理
- 类名：`Initializer`
- 入口方法：`initialize(npc_name, character_profile)`
- prompt文件：无（代码硬编码）
- 处理内容：
  1. 设置 npc_name
  2. 加载角色设定 character_profile
  3. 调用 LLM 生成初始场景（_generate_scene_archive）
  4. 设置初始六轴

### 数据流
- 输入：character_profile（角色设定）
- 输出：scene_archive（场景档案）
- 存储位置：engine.state.scene_archive（内存）

### 六轴更新
- 初始六轴值：
  - Intimacy: 2
  - Risk: 2
  - Info: 2
  - Action: 2
  - Rel: 1
  - Growth: 2
- 文件存储：无

### GUI显示
- 无对应标签页

---

## 2. PerceptionLayer（感知层）

### 引擎处理
- 类名：`PerceptionLayer`
- 入口方法：`analyze(user_input)`
- prompt文件：`roles/perception.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/perception.md
- 内容：用户输入分析规则

**user prompt：**
```
角色设定（截取10000字符）：
{npc_context[:10000]}

用户输入：
{user_input}
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从配置获取

#### LLM返回
- 原始输出：JSON格式字符串
- 解析后字段：
  - user_intent：用户意图
  - user_emotion：用户情感
  - initiative：主动性（1-5）
  - hidden_meaning：隐藏意图
  - key_entities：关键实体

### 数据流
- 输入：user_input（用户输入）
- 输出：Perception对象
- 传给下模块：DirectorLayer

### 六轴更新
- 无

### 文件存储
- 无

### GUI显示
- 标签页：Perception
- input组件：
  - 类型：Text（只读）
  - 内容：拼接后的完整 prompt（system + user）
  - 更新逻辑：self.perception_input = 完整prompt字符串
- output组件：
  - 类型：Text（只读）
  - 内容：LLM原始输出
  - 更新逻辑：self.perception_output = raw_output

---

## 3. DirectorLayer（导演层）

### 引擎处理
- 类名：`DirectorLayer`
- 入口方法：`direct(user_input, perception_result)`
- prompt文件：`roles/director.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/director.md
- 内容：STORY_PATCH生成规则

**user prompt：**
```
NPC角色设定（截取10000字符）：
{npc_context[:10000]}

六轴状态：
{axes_str}

对话历史（最近10轮）：
{history_str}

用户输入：
{user_input}
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从配置获取

#### LLM返回
- 原始输出：JSON格式字符串
- 解析后字段：
  - narrative_level：叙事等级（L0/L1/L2）
  - focus：重点体验
  - logic_subtext：潜文本
  - thread_to_touch：关联线程
  - patch_status：状态（HOLD/EVOLVE/PIVOT/STALL）
  - beat_plan：节拍计划
  - tension_tools：张力工具
  - hook：钩子

### 数据流
- 输入：Perception输出 + 六轴状态 + 对话历史
- 输出：STORY_PATCH对象
- 传给下模块：PerformerLayer

### 六轴更新
- 调用apply_state_update()更新engine.state.axes
- 更新逻辑：从STORY_PATCH中解析STATE_UPDATE_JSON

### 文件存储
- 调用save_state()保存到state_{role_id}.json

### GUI显示
- 标签页：Director
- input组件：
  - 类型：Text（只读）
  - 内容：拼接后的完整 prompt
  - 更新逻辑：self.director_input = 完整prompt字符串
- output组件：
  - 类型：Text（只读）
  - 内容：LLM原始输出
  - 更新逻辑：self.director_output = raw_output

---

## 4. PerformerLayer（表演层）

### 引擎处理
- 类名：`PerformerLayer`
- 入口方法：`perform(user_input, story_patch)`
- prompt文件：`roles/performer.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/performer.md
- 内容：NPC对话生成规则

**user prompt：**
```
角色设定：
{role_content[:10000]}

六轴状态：
{axes_str}

对话历史：
{history_str}

用户输入：
{user_input}

STORY_PATCH：
{story_patch_str}
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从配置获取

#### LLM返回
- 原始输出：NPC对话文本
- 解析后：直接返回文本

### 数据流
- 输入：STORY_PATCH + 用户输入 + 六轴状态
- 输出：NPC对话文本
- 传给下模块：无（主流程结束）

### 六轴更新
- 无

### 文件存储
- 无（对话历史由GUI保存）

### GUI显示
- 标签页：Performer
- input组件：
  - 类型：Text（只读）
  - 内容：拼接后的完整 prompt
  - 更新逻辑：self.performer_input = 完整prompt字符串
- output组件：
  - 类型：Text（只读）
  - 内容：LLM原始输出
  - 更新逻辑：self.performer_output = raw_output

---

## 5. NEHPredictor（事件预测）

### 引擎处理
- 类名：`NEHPredictor`
- 入口方法：`generate_event_card()`
- prompt文件：`roles/predictor.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/predictor.md
- 内容：事件卡生成规则

**user prompt：**
```
六轴状态：
{axes_str}

对话历史：
{history_str}

用户输入：
{user_input}

Director决策：
{director_output}
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从配置获取

#### LLM返回
- 原始输出：JSON格式字符串
- 解析后字段：
  - event_id：事件ID
  - archetype：事件原型
  - trigger_condition：触发条件
  - impact：影响
  - priority：优先级

### 数据流
- 输入：六轴 + 对话历史 + Director输出
- 输出：候选事件卡
- 传给下模块：NEHEventPool

### 六轴更新
- 无

### 文件存储
- 无

### GUI显示
- 标签页：Predictor
- input组件：
  - 类型：Text（只读）
  - 内容：拼接后的完整 prompt
  - 更新逻辑：self.predictor_input = 完整prompt字符串
- output组件：
  - 类型：Text（只读）
  - 内容：LLM原始输出
  - 更新逻辑：self.predictor_output = raw_output
- 特殊：异步执行，结果在下一轮显示

---

## 6. NEHEventPool（事件池）

### 引擎处理
- 类名：`NEHEventPool`
- 主要方法：
  - add(event)：添加事件
  - cleanup_low_priority(round_num)：清理低优先级
  - get_all()：获取所有事件
  - remove_triggered()：移除已触发事件

### 数据流
- 输入：NEHPredictor生成的候选事件
- 输出：待触发事件列表

### 六轴更新
- 无

### 文件存储
- 无

### GUI显示
- 标签页：无独立标签页
- 事件卡显示：GUI右侧事件卡面板

---

## 7. ObserverLayer（观察层）

### 引擎处理
- 类名：`ObserverLayer`
- 入口方法：`evaluate(conversation_history, npc_reply)`
- prompt文件：`roles/observer.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/observer.md
- 内容：对话质量评估规则

**user prompt：**
```
对话历史：
{history_str}

用户输入：
{user_input}

NPC回复：
{npc_reply}
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从配置获取

#### LLM返回
- 原始输出：JSON格式字符串
- 解析后字段：
  - emotion_curve：情感曲线评分
  - suspense：悬疑评分
  - memory：记忆评分
  - immersion：沉浸评分
  - summary：总结

### 数据流
- 输入：对话历史 + NPC回复
- 输出：质量评估结果

### 六轴更新
- 无

### 文件存储
- 无

### GUI显示
- **注意**：Observer 不是自动显示的标签页
- 触发方式：用户点击菜单"分析对话"按钮手动触发
- 显示位置：直接在聊天窗口输出评估结果

---

## 数据流总览

```
用户输入
    ↓
[Initializer] → 初始化场景、设置六轴（仅首次）
    ↓
[Perception] → 分析用户输入 → 分析结果
    ↓
[Director] → 生成STORY_PATCH → 更新六轴 → 保存存档
    ↓
[Performer] → 生成NPC回复
    ↓
[Observer] → 评估对话质量（手动触发）
    ↓
[NEHPredictor] → 异步生成候选事件 → [NEHEventPool]
```

---

## 附加模块：Performer Direct（直通模型）

### 说明
这是绕过叙事引擎直接调用 LLM 的功能，用于对比测试。

### 引擎处理
- 方法：`send_message_direct()` (在 main.py 中定义)
- prompt文件：`roles/performer_direct.md`

#### prompt构建细节
**system prompt：**
- 来源：roles/performer_direct.md

**user prompt：**
```
角色设定：
{role_content}

# 对话历史
{conversation_history (去掉最后一轮)}

现在请继续对话。
```

**LLM调用：**
- messages格式：[{"role":"system", "content": system_prompt}, {"role":"user", "content": user_prompt}]
- model：从界面模型选择器获取

#### API 配置获取
由于是直通模式，需要手动获取 API 配置：
```python
# 从 MODELS_CONFIG 中获取当前 provider 的配置
from engine_llm import MODELS_CONFIG, CURRENT_PROVIDER

# 从 selected_model 中提取 provider（如 "doubao:doubao-1-5-pro-32k" -> "doubao"）
provider = selected_model.split(':')[0] if ':' in selected_model else CURRENT_PROVIDER

# 获取对应 provider 的配置
provider_config = MODELS_CONFIG.get("providers", {}).get(provider, {})
api_config = {
    "api_key": provider_config.get("api_key", ""),
    "base_url": provider_config.get("api_url", "https://api.minimax.chat/v1"),
    "default_model": provider_config.get("default_model", selected_model)
}
```

#### API 调用方式
使用 urllib.request（与引擎一致），不要用 requests 库：
```python
import urllib.request
import json

url = api_config.get('base_url')  # 直接使用 provider 的 api_url，不要拼接路径

payload = {
    "model": api_config.get('default_model', selected_model),
    "messages": [
        {"role": "system", "content": performer_direct_prompt},
        {"role": "user", "content": user_prompt}
    ],
    "temperature": 0.7
}
data = json.dumps(payload).encode('utf-8')

req = urllib.request.Request(url, data=data, method='POST')
req.add_header("Authorization", f"Bearer {api_key}")
req.add_header("Content-Type", "application/json")

response = urllib.request.urlopen(req, timeout=60)
result = json.loads(response.read().decode('utf-8'))

if 'choices' in result and len(result['choices']) > 0:
    npc_reply = result['choices'][0]['message']['content']
elif 'error' in result:
    raise Exception(f"API错误: {result['error']}")
else:
    raise Exception(f"未知响应: {result}")
```

### 特点
- 不更新六轴
- 不保存对话历史
- 不调用 predictor
- 历史记录去掉最后一轮（用于对比测试）

### GUI显示
- 标签页：Performer Direct
- input组件：完整 prompt
- output组件：LLM原始输出


---

## 关键文件

### 引擎核心
- logic/engine/engine_llm.py - 引擎实现
- logic/engine/state.py - 状态管理（SessionStateManager）

### GUI 原型
- logic/prototype/main.py - GUI 主程序

### Prompt 文件
- logic/roles/perception.md - 感知层
- logic/roles/director.md - 导演层
- logic/roles/performer.md - 表演层
- logic/roles/predictor.md - 事件预测
- logic/roles/observer.md - 对话评估
- logic/roles/performer_direct.md - 直通模型

### 配置文件
- logic/config.json - 基础配置
- logic/models_config.json - 模型配置
- logic/prototype/config.json - GUI 配置

### 存档与日志
- logic/save/state_{role_id}.json - 角色状态存档
- logic/prototype/logs/chat_{role_id}.txt - 对话历史
- logic/prototype/logs/debug/ - 调试日志

---

## 操作说明

### 引擎模式（发送按钮）
1. 用户输入 -> Perception分析 -> Director生成STORY_PATCH -> Performer生成回复
2. 六轴自动更新并保存
3. 对话历史自动保存

### 直通模型模式（直通模型按钮）
1. 直接调用 LLM，不经过叙事引擎
2. 不更新六轴
3. 不保存对话历史
4. 历史记录去掉最后一轮（用于对比测试）

### 手动触发
- Observer：点击分析按钮手动评估对话质量
