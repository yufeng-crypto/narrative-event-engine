# NPC Chat Prototype - 系统说明文档

## 1. 概述

NPC Chat Prototype 是一个本地 Windows GUI 程序，用于与 AI NPC 角色进行对话交互。

**仅支持引擎模式**：使用统一的 `engine_llm.py` 核心引擎，执行完整的三层架构流程

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│              NPC Chat Prototype (main.py)                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   GUI 层 (tkinter)                  │    │
│  │  - 角色选择    - 对话窗口    - 输入框              │    │
│  │  - 六轴显示    - 事件卡显示  - 调试标签页          │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌───────────────────────┴───────────────────────────┐      │
│  │                  对话管理                          │      │
│  │  - 历史记录加载/保存    - 状态管理    - 消息发送  │      │
│  └───────────────────────┬───────────────────────────┘      │
└──────────────────────────┼────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    引擎模式 (engine_llm.py)                  │
├─────────────────────────────────────────────────────────────┤
│ SessionStateManager (状态枢纽)                               │
│ - 六轴数值    - 动量    - 线程池    - 事件卡池              │
├─────────────────────────────────────────────────────────────┤
│ 三层架构流程:                                                │
│   PerceptionLayer (感知层) → DirectorLayer (导演层)         │
│              → PerformerLayer (表演层)                      │
│   + NEHPredictor (事件卡预测, 每5轮)                        │
│   + NEHTrigger (事件触发判定)                               │
└─────────────────────────────────────────────────────────────┘
├─────────────────────┤        ├─────────────────────────────┤
│ Performer          │        │ PerceptionLayer              │
│ (NPC对话)          │        │ (用户感知)                  │
├─────────────────────┤        ├─────────────────────────────┤
│ Observer           │        │ DirectorLayer               │
│ (质量评估)         │        │ (数值计算)                  │
├─────────────────────┤        ├─────────────────────────────┤
│ (无)               │        │ PerformerLayer             │
│                    │        │ (对话渲染)                  │
├─────────────────────┤        ├─────────────────────────────┤
│ (无)               │        │ NEHPredictor                │
│                    │        │ (事件卡生成)                │
├─────────────────────┤        ├─────────────────────────────┤
│ (无)               │        │ NEHEventPool                │
│                    │        │ (事件池管理)                │
├─────────────────────┤        ├─────────────────────────────┤
│ (无)               │        │ NEHTrigger                 │
│                    │        │ (触发判定)                  │
└─────────────────────┘        └─────────────────────────────┘
```

---

## 3. GUI 界面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  [角色选择 ▼]                              [发送] [保存] [分析]   │
├────────────────────────────────┬─────────────────────────────────┤
│                                │  ┌─────────────────────────┐   │
│                                │  │ [Perception] [Director]│   │
│       对话窗口                 │  │ [Predictor] [Performer]│   │
│                                │  ├─────────────────────────┤   │
│                                │  │ 【输入】                 │   │
│                                │  │ SYSTEM: ...             │   │
│                                │  │ USER: ...               │   │
│                                │  ├─────────────────────────┤   │
│                                │  │ 【输出】                 │   │
│                                │  │ LLM返回结果...           │   │
│                                │  └─────────────────────────┘   │
├────────────────────────────────┼─────────────────────────────────┤
│  [输入框...............]        │  [六轴状态]  [事件卡]         │
│                                │  Intimacy: ████░░ 6           │
└────────────────────────────────┴─────────────────────────────────┘
```

### 3.1 调试标签页（核心更新）

**四个模块各一个标签页：Perception / Director / Predictor / Performer**

每个标签页内包含两个调试窗口：

| 窗口 | 背景色 | 说明 |
|------|--------|------|
| 【输入】发送给LLM的内容 | 浅蓝色 `#e8f0f8` | **完整prompt**（见下方详细说明） |
| 【输出】LLM返回结果 | 浅绿色 `#f0f8e8` | LLM 的原始返回内容 |

---

### 3.2 调试窗口显示逻辑（核心设计原则）

**这是叙事引擎提示词工程模块的实际运行方式，必须严格遵循：**

#### 3.2.1 【输入】窗口显示内容定义

**【输入】显示的是：将模板与变量值拼接后，发送给LLM的完整prompt内容**

具体逻辑：
1. 读取对应模块的提示词模板文件（`perception.md` / `director.md` / `predictor.md` / `performer.md`）
2. 将程序运行时的实际变量值填充到模板中
3. 拼接后的完整文本，就是发送给LLM的输入

**Perception【输入】包含内容：**
```
[perception.md 模板内容]
+
NPC设定 (character_profile[:300])
+
对话历史 (最近几轮)
+
用户输入 (user_input)
```

**Perception【输出】包含内容：**
```
{
  "initiative": 0-3,      # 用户主动性
  "intent": "Story/Chat/Verify/Conflict",  # 交互意图
  "emotion_tone": "Warm/Teasing/Neutral/...",  # 情感调性
  "stall": 0-3,           # 停滞分数
  "dominance": "User-Led/NPC-Led/Balanced",  # 权力重心
  "hidden_meaning": "..."  # 隐藏含义
}
```

**Director【输入】包含内容：**
```
[director.md 模板内容]
+
角色设定 (character_profile)
+
对话历史 (最近10轮)
+
当前六轴状态 (axes)
+
动量 (momentum)
+
线程池 (threads)
+
用户输入分析结果 (perception)
+
NEH事件信息 (如果有)
+
"请输出JSON。"
```

**Predictor【输入】包含内容：**
```
[predictor.md 模板内容]
+
当前六轴状态 (axes)
+
用户主动性均值 (avg_initiative)
+
母版库 (NEH_ARCHETYPES)
+
"只输出JSON。"
```

**Performer【输入】包含内容：**
```
[performer.md 模板内容]
+
角色设定 (character_profile)
+
六轴状态 (axes)
+
STORY_PATCH (JSON格式)
+
用户输入 (user_input)
+
"直接输出角色对话。"
```

#### 3.2.2 【输出】窗口显示内容定义

**【输出】显示的是：LLM收到上述【输入】后，返回的原始内容**

- Director【输出】= LLM返回的STORY_PATCH（可能是JSON或文本格式）
- Predictor【输出】= LLM返回的事件卡数据（JSON格式）
- Performer【输出】= LLM返回的NPC对话内容

#### 3.2.3 技术实现

引擎模块（engine_llm.py）中，每个模块类都实现了：
```python
def get_last_full_prompt(self) -> str:
    """返回最后一次使用的完整prompt（用于调试显示）"""
    return self._last_full_prompt
```

在调用LLM之前，将构建的完整prompt保存到 `self._last_full_prompt`，GUI通过 `result.get('director_input')` 获取并显示。

---

## 4. 核心功能

### 4.1 角色管理
- 从 `roles/npc_*.md` 加载角色设定
- 支持多角色切换
- 每个角色有独立的六轴初始值

### 4.2 对话模式

#### 传统模式流程：
```
用户输入 → Predictor(事件卡) → Director(STORY_PATCH) → Performer(NPC回复) → Observer(评估)
```

#### 引擎模式流程：
```
用户输入 
  → PerceptionLayer(感知: 主动性/意图/情感/停滞分)
  → NEHPredictor(事件卡生成, 每5轮)
  → NEHTrigger(触发判定)
  → DirectorLayer(生成STORY_PATCH)
  → PerformerLayer(对话渲染)
  → NPC回复
```

### 4.3 六轴系统

| 轴名 | 范围 | 说明 |
|------|------|------|
| Intimacy | 0-10 | 亲密度 |
| Risk | 0-10 | 风险值 |
| Info | 0-10 | 信息量 |
| Action | 0-10 | 行动力 |
| Rel | 0-10 | 关系值 |
| Growth | 0-10 | 成长度 |

### 4.4 历史记录
- 自动保存路径：`prototype/logs/chat_{role_id}.txt`
- 手动保存：支持另存为
- 加载格式：`[时间戳] 角色名: 内容`

### 4.5 Debug 日志系统（新增）

- **日志目录**: `prototype/logs/debug/`
- **日志文件**: `debug_YYYYMMDD_HHMMSS.log`

**日志级别**:
- `[INFO]` - 正常流程
- `[DEBUG]` - 详细信息
- `[ERROR]` - 错误信息

**日志标签**:
- `[MAIN]` - 主程序
- `[ENGINE]` - 引擎加载
- `[PERFORMER]` - Performer API调用
- `[DIRECTOR]` - Director API调用
- `[PREDICTOR]` - Predictor API调用

**每个API请求记录**:
1. 请求前：开始调用、API配置检查、提示词加载
2. 请求时：URL、Headers（已隐藏敏感信息）、请求体
3. 响应后：状态码、响应内容预览
4. 异常时：完整的错误信息和堆栈

---

## 5. 关键文件

| 文件 | 说明 |
|------|------|
| `main.py` | GUI主程序 |
| `engine_wrapper.py` | 引擎对接层 |
| `engine_llm.py` | 核心引擎（v3.0） |
| `config.json` | 配置文件 |
| `logs/` | 对话历史 |
| `logs/debug/` | Debug日志 |
| `roles/` | NPC角色设定 |

---

## 6. 功能清单

### 6.1 界面功能
- [x] 角色选择下拉框
- [x] 角色切换
- [x] 聊天消息显示
- [x] 消息输入框
- [x] 发送按钮
- [x] 六轴进度条显示
- [x] 事件卡显示
- [x] **调试标签页（Director/Predictor/Performer）** ← 新增
- [x] **输入窗口区分SYSTEM/USER** ← 新增
- [x] 系统消息显示

### 6.2 对话功能
- [x] 传统模式对话
- [x] 引擎模式对话
- [x] 引擎模式回退到传统模式
- [x] 历史记录加载（支持多行）
- [x] 自动保存对话
- [x] 手动保存对话
- [x] 新对话重置

### 6.3 分析功能
- [x] Observer 对话质量评估（传统模式）
- [x] 评分显示（逻辑/方法论/沉浸感/风险）

### 6.4 调试功能
- [x] **完整Debug日志系统** ← 新增
- [x] API请求/响应记录
- [x] 异常堆栈跟踪

---

## 7. 配置说明

```json
{
  "api": {
    "provider": "minimax",
    "api_key": "xxx",
    "base_url": "https://api.minimax.chat/v1",
    "model": "MiniMax-M2.5"
  },
  "roles_path": "roles目录路径",
  "logs_path": "日志目录路径"
}
```

---

## 8. 测试要点

### 8.1 GUI测试
- [x] 角色选择与切换
- [x] 消息发送与接收
- [x] 历史记录加载（多行）
- [x] 六轴显示更新
- [x] 事件卡显示更新
- [x] **调试标签页切换** ← 新增
- [x] **输入窗口SYSTEM/USER格式** ← 新增

### 8.2 对话质量测试
- [ ] 角色一致性
- [ ] 情绪表达能力
- [ ] 多轮对话连贯性

### 8.3 引擎模式测试
- [x] 引擎初始化
- [ ] 对话响应时间
- [x] 轴值动态变化
- [x] NEH事件触发显示
- [x] 预览面板更新

### 8.4 Debug日志测试
- [x] 日志文件生成
- [x] API请求记录
- [x] 异常日志记录 ← 新增

---

## 9. 已知问题

1. 引擎模式响应较慢（3层LLM调用）
2. 历史加载正则需适配不同格式
3. 切换角色时可能有延迟
4. Observer 分析仅支持传统模式

---

## 10. API 接口（engine_llm.py）

```python
from engine_llm import create_engine, start_engine, chat, get_state

# 创建引擎
engine = create_engine()

# 初始化
start_engine(engine, "角色ID", "角色设定")

# 对话
result = chat(engine, "用户消息")

# 获取状态
state = get_state(engine)
# state = { axes, momentum, threads, event_pool, round, avg_initiative }
```

---

## 11. 更新日志

### 2026-03-02 (第九版)
- **六轴存档加载优化**：
  - 程序启动时自动加载 `state_{role_id}.json` 存档
  - 切换角色时重新加载对应角色的存档
  - 每轮对话更新策略保持不变（引擎返回值实时更新）
- **Performer 模型切换修复**：
  - 修复模型名称解析 bug：GUI传入 `doubao:xxx` 格式
  - 修复前：直接匹配失败（`doubao:xxx` in [`xxx`] = False）
  - 修复后：提取纯模型名 `model.split(":")[-1]` 再匹配
- **调试窗口显示原始输出**：
  - 4个模块(Predictor/Perception/Director/Performer)的output窗口
  - 现在显示 LLM 原始输出，而非解析后的JSON
  - 便于调试和分析LLM返回内容
- **NEH_INTERVAL 调试设置**：
  - 改为 `1`（每轮都执行），便于测试
  - ⚠️ 待调试完成后改回 `5`

### 2026-03-02 (第八版)
- **NEH-Predictor 对话历史增强**：
  - Predictor 的 user prompt 中新增对话历史（最近10轮）
  - 格式与 Director 一致："用户: xxx" / "NPC: xxx"
  - 使 NEH 事件生成更精准地结合上下文
- **NEH-Predictor 简化Prompt**：
  - 移除 user prompt 中的母版库内容
  - 减少 Prompt 长度，提高生成效率

### 2026-03-02 (第七版)
- **运行速度监控**：
  - GUI新增「运行速度」监控窗口，显示每轮对话各模块耗时
  - 事件卡窗口高度减半，下方新增运行速度窗口
  - 各模块详细计时：
    - Perception：准备上下文、获取历史、构建Prompt、LLM调用、解析结果
    - Director：获取轴和动量、获取线程、获取历史、获取角色上下文、构建Prompt、LLM调用
    - Performer：获取角色上下文、获取轴数据、构建Prompt
- **对话历史优化**：
  - 感知层和导演层的对话历史改为获取最近10轮（之前是3轮）
  - 去掉历史内容截断限制（之前每条只显示前30字符）
  - 格式改为"用户: xxx"和"NPC: xxx"
- **模型配置功能**：
  - 新增模型选择下拉框，支持 minimax 和火山引擎 doubao
  - 模型配置文件：`logic/models_config.json`
  - 仅 Performer 模块使用选择模型，其他模块继续使用 minimax
- **Director/Predictor 解析优化**：
  - 支持解析嵌套格式（如 `pending_events[]`）
  - STORY_PATCH 输出显示原始内容
- **其他优化**：
  - 修复引擎重复创建导致 MODEL 被重置的问题
  - 使用 `get_current_model()` 函数获取实时模型配置

### 2026-03-01 (第六版)
- **Prompt格式优化**：MD模板放到system prompt，参数放到user prompt
- **调试窗口升级**：各模块输入窗口区分显示 SYSTEM 和 USER 两部分
- **引擎代码修改**：
  - 各模块新增 `get_last_prompt_parts()` 方法，返回 system 和 user 两部分
  - `call_llm()` 调用改为传入 system 和 user 两条消息

### 2026-03-01 (第五版)
- **移除传统模式**：删除所有传统模式相关代码，强制使用引擎模式走三层架构
- **角色状态保存改进**：
  - 状态文件改为按角色分开：`state_{role_id}.json`（如 `state_shenyuxi.json`）
  - 不再所有角色共用一个文件
- **初始化流程优化**：
  - 引擎初始化前先检查角色存档是否存在
  - 存档存在时检查有效性（axes范围0-10, momentum范围-2~+2, round>=0, npc_name/scene_archive非空）
  - 无效存档时弹出对话框让用户选择：
    - 选择"是" → 执行初始化（生成场景档案、初始六轴、首个STORY_PATCH）
    - 选择"否" → 取消发送，停止初始化流程
- **engine_llm.py新增**：`validate_save_data()` 方法用于验证存档有效性

### 2026-02-28 (第四版)
- **新增Perception标签页**：添加Perception模块的调试窗口，显示输入（拼接prompt）和输出（LLM返回结果）
- **调试窗口扩展**：从3个模块扩展到4个模块（Perception/Director/Predictor/Performer）
- **引擎代码修改**：PerceptionLayer新增`get_last_full_prompt()`方法，run_turn返回perception_input和perception_output

### 2026-02-28 (第三版)
- **调试窗口显示逻辑修正**：明确【输入】显示的是"完整prompt"（模板+变量值拼接后），【输出】显示的是"LLM返回的原始内容"
- **引擎代码修改**：DirectorLayer、NEHPredictor、PerformerLayer新增`get_last_full_prompt()`方法，返回完整拼接后的prompt
- **技术实现说明**：详细描述了三个模块的输入输出具体包含哪些内容

### 2026-02-28 (第一版)
- **GUI优化**：将三个角色的调试窗口改为标签页形式（Director/Predictor/Performer）
- **输入显示优化**：每个标签页区分【输入】和【输出】两个窗口，输入窗口清晰展示SYSTEM和USER两部分
- **Debug日志系统**：添加完整的日志记录，记录每个API的请求/响应，便于问题排查

---

*最后更新: 2026-03-01*

---

## 附录：GUI 控件变量清单

### 顶部区域 (Top Frame)
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| `role_var` | tk.StringVar | 角色选择下拉框绑定的变量 |
| `role_combo` | ttk.Combobox | 角色下拉选择框 |

### 按钮区域 (Button Frame)
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| (按钮) | ttk.Button | "发送" - 触发 send_message() |
| (按钮) | ttk.Button | "保存" - 触发 save_conversation() |
| (按钮) | ttk.Button | "分析" - 触发 analyze_conversation() |
| (按钮) | ttk.Button | "新对话" - 触发 start_new_chat() |

### 左侧区域 - 对话区 (Left Frame)
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| `chat_text` | scrolledtext.ScrolledText | 聊天记录显示区域（滚动） |
| `input_text` | tk.Text | 用户输入框（多行，height=3） |

### 中间区域 - 调试标签页 (Middle Frame)
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| `debug_notebook` | ttk.Notebook | 调试标签页容器 |
| `perception_tab` | ttk.Frame | Perception 调试标签页 |
| `director_tab` | ttk.Frame | Director 调试标签页 |
| `predictor_tab` | ttk.Frame | Predictor 调试标签页 |
| `performer_tab` | ttk.Frame | Performer 调试标签页 |
| `perception_input_text` | tk.Text | Perception 输入内容显示 |
| `perception_output_text` | tk.Text | Perception 输出内容显示 |
| `director_input_text` | tk.Text | Director 输入内容显示 |
| `director_output_text` | tk.Text | Director 输出内容显示 |
| `predictor_input_text` | tk.Text | Predictor 输入内容显示 |
| `predictor_output_text` | tk.Text | Predictor 输出内容显示 |
| `performer_input_text` | tk.Text | Performer 输入内容显示 |
| `performer_output_text` | tk.Text | Performer 输出内容显示 |

### 右侧区域 (Right Frame)
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| `axis_labels` | dict | 六轴状态标签字典 {轴名: {"progress": Progressbar, "value": Label}} |
| `event_card_text` | tk.Text | 事件卡显示区域 |

### 底部状态栏
| 变量名 | 控件类型 | 作用 |
|--------|----------|------|
| `status_var` | tk.StringVar | 状态栏文字变量 |

### 数据变量
| 变量名 | 类型 | 作用 |
|--------|------|------|
| `axes_data` | dict | 六轴数值 {Intimacy, Risk, Info, Action, Rel, Growth} |
| `event_card` | dict | 当前事件卡数据 {event_id, archetype, title, trigger, plot_hook} |
| `conversation_history` | list | 对话历史 [{"role": "user/assistant", "content": "..."}] |
| `engine` | Engine | 叙事引擎实例 |
