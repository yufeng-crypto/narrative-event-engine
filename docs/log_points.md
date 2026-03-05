# 日志记录点汇总

> 本文档梳理程序中所有日志记录点，按模块和程序分类

---

## 一、日志函数定义

### main.py (GUI程序)

| 函数 | 输出级别 | 输出位置 | 用途 |
|------|---------|---------|------|
| `log_info()` | INFO | 文件 + 控制台 | 普通信息 |
| `log_error()` | ERROR | 文件 + 控制台 | 错误信息 |
| `log_debug()` | DEBUG | 文件 + 控制台 | 调试信息 |
| `log_api_request()` | DEBUG | 文件 | API请求 |
| `log_api_response()` | DEBUG | 文件 | API响应 |

### engine_llm.py (引擎)

| 函数 | 输出级别 | 输出位置 | 用途 |
|------|---------|---------|------|
| `log_to_file()` | - | 文件 | 写入日志文件 |
| `print()` | - | 控制台 | 调试输出（混乱） |

---

## 二、按模块分类

### 2.1 模块：模型配置

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | set_model() | MODEL, CURRENT_PROVIDER | log_to_file | ✅ 保留 |
| main.py | 选择模型 | MODELS_CONFIG | log_info | ✅ 保留 |

**重复性**: 无

---

### 2.2 模块：LLM调用

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | call_llm() | 使用的模型、provider切换 | log_to_file | ✅ 保留 |
| main.py | call_xxx_api() | API请求、响应 | log_api_request/response | ✅ 保留 |
| main.py | 各模块 | 开始调用、调用成功、API错误 | log_info/log_error | ✅ 保留 |

**重复性**: 
- engine_llm.py 和 main.py 都记录了 API 调用，但角度不同
- engine_llm.py 记录底层请求
- main.py 记录上层业务

---

### 2.3 模块：Initializer

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | start() | === aibaji Engine v3.0 === | print | ✅ 保留（启动标识） |
| engine_llm.py | start() | NPC名称 | print | ❌ 删除（调试信息） |
| engine_llm.py | start() | 场景档案 | print | ❌ 删除（调试信息） |

**重复性**: 无

---

### 2.4 模块：Perception

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | run_turn() | 每轮开始 Round N | print | ✅ 保留 |
| engine_llm.py | run_turn() | 用户输入 | print | ❌ 删除（调试信息） |
| engine_llm.py | analyze() | initiative, intent, stall | print | ❌ 删除（过于详细） |

**重复性**: 无

---

### 2.5 模块：Director

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | direct() | 当前六轴 | print | ❌ 删除（过于详细） |
| engine_llm.py | direct() | NEH影响 | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | STATE_UPDATE | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | perception_str | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | prompt前200字 | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | LLM原始输出 | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | STORY_PATCH | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | STATE_UPDATE JSON解析 | print | ❌ 删除（调试信息） |
| engine_llm.py | direct() | 使用降级逻辑 | print | ❌ 删除（调试信息） |
| engine_llm.py | apply_state_update() | axes_next | print | ❌ 删除（调试信息） |
| engine_llm.py | apply_state_update() | axis_changes | print | ❌ 删除（调试信息） |
| engine_llm.py | apply_state_update() | momentum_next | print | ❌ 删除（调试信息） |
| engine_llm.py | apply_state_update() | 最终六轴值 | print | ❌ 删除（调试信息） |
| main.py | call_director_api() | 开始调用 | log_info | ✅ 保留 |
| main.py | call_director_api() | prompt文件路径 | log_debug | ❌ 删除（调试信息） |
| main.py | call_director_api() | 使用降级逻辑 | log_debug | ❌ 删除（调试信息） |
| main.py | call_director_api() | 事件信息 | log_debug | ❌ 删除（调试信息） |
| main.py | call_director_api() | 调用成功 | log_info | ✅ 保留 |
| main.py | call_director_api() | API错误 | log_error | ✅ 保留 |

**重复性**: ⚠️ engine_llm.py 和 main.py 都有 Director 相关日志，但位置不同

---

### 2.6 模块：Performer

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | perform() | beat, focus | print | ❌ 删除（调试信息） |
| engine_llm.py | perform() | NPC回复 | print | ❌ 删除（调试信息） |
| main.py | call_performer_api() | 开始调用LLM | log_info | ✅ 保留 |
| main.py | call_performer_api() | 调用成功 | log_info | ✅ 保留 |
| main.py | call_performer_api() | API错误 | log_error | ✅ 保留 |

**重复性**: 无

---

### 2.7 模块：Predictor

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | run_turn() | 触发事件 | print | ❌ 删除（调试信息） |
| engine_llm.py | run_predictor_async() | 生成事件 | print | ❌ 删除（调试信息） |
| engine_llm.py | run_predictor_async() | 生成失败 | print | ❌ 删除（调试信息） |
| engine_llm.py | run_turn() | 读取上一轮结果 | print | ❌ 删除（调试信息） |
| engine_llm.py | run_turn() | axes after update | print | ❌ 删除（调试信息） |
| main.py | call_predictor_api() | 开始调用 | log_info | ✅ 保留 |
| main.py | call_predictor_api() | 调用成功 | log_info | ✅ 保留 |
| main.py | call_predictor_api() | API错误 | log_error | ✅ 保留 |

**重复性**: 无

---

### 2.8 模块：状态保存

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| engine_llm.py | save_debug() | 写入成功/失败 | print | ❌ 删除（调试信息） |
| engine_llm.py | save_debug() | timing信息 | print | ❌ 删除（调试信息） |
| main.py | save_conversation() | 保存对话 | log_info | ✅ 保留 |

**重复性**: 无

---

### 2.9 模块：GUI操作

| 程序 | 位置 | 记录内容 | 输出 | 处理建议 |
|------|------|---------|------|---------|
| main.py | __init__ | 日志文件路径 | log_info | ✅ 保留 |
| main.py | 切换模型 | 选择模型 | log_info | ✅ 保留 |
| main.py | 更新调试窗口 | 各模块input/output | log_info | ✅ 保留 |

**重复性**: 无

---

## 三、问题汇总

### 3.1 主要问题

| 问题 | 说明 |
|------|------|
| print 过多 | engine_llm.py 中有 30+ 处 print，大部分是调试信息 |
| 重复记录 | engine_llm.py 和 main.py 重复记录同一模块 |
| 过于详细 | 大量 prompt 切片、中间状态打印 |
| 输出分散 | 控制台 + 文件，日志分散 |

### 3.2 处理建议

1. **删除所有调试 print**：engine_llm.py 中大部分 print 可以删除
2. **统一日志函数**：engine_llm.py 也使用 log_to_file() 或引入 main.py 的日志函数
3. **只保留关键节点**：
   - 引擎启动
   - 每轮开始
   - 模块调用前/后
   - 错误信息
4. **删除过于详细的**：
   - prompt 切片
   - 中间状态数值
   - 降级逻辑提示

---

## 四、建议的日志节点

### 4.1 engine_llm.py 应该保留的日志

| 模块 | 节点 | 内容 | 输出 |
|------|------|------|------|
| 引擎 | start() | === aibaji Engine v3.0 === | log_to_file |
| 引擎 | run_turn() | === Round N === | log_to_file |
| Director | direct() | 调用LLM | log_to_file |
| Director | direct() | 调用成功 | log_to_file |
| Director | direct() | 调用失败 | log_to_file |
| Performer | perform() | 调用LLM | log_to_file |
| Performer | perform() | 调用成功 | log_to_file |
| Performer | perform() | 调用失败 | log_to_file |

### 4.2 main.py 应该保留的日志

| 模块 | 节点 | 内容 | 输出 |
|------|------|------|------|
| GUI | 启动 | 日志文件路径 | log_info |
| 模型 | 切换 | 选择模型 | log_info |
| Director | 调用前 | 开始调用 | log_info |
| Director | 调用后 | 调用成功 | log_info |
| Director | 错误 | API失败 | log_error |
| Performer | 调用前 | 开始调用 | log_info |
| Performer | 调用后 | 调用成功 | log_info |
| Performer | 错误 | API失败 | log_error |
| 保存 | 对话 | 保存成功 | log_info |

---

## 五、实施建议

### 5.1 立即可做

1. 删除 engine_llm.py 中所有 `print()` 语句
2. 在关键节点添加 `log_to_file()`

### 5.2 长期优化

1. 统一日志函数（engine_llm.py 引用 main.py 的日志）
2. 删除过于详细的调试信息
3. 统一日志格式
