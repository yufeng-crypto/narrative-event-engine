# character_pursuits + UAR · 工作流节点级设计 v3

> 日期：2026-04-21（含 2026-04-21 晚 closed-loop guard 修订）
> 配合：`dify_node_conventions_cheatsheet.md`（节点规范）+ `character_pursuits_design_v0.md`（总设计）+ `user_assist_request_design_v0.md`（UAR 子设计）+ `pursuits_input_contract_v1.md`（输入契约沉淀）
>
> 本版目的：**所有与 v3 工作流相关的事实在本文内闭环**，不再引用 v2/v1。用于 Day 1 / Day 2 实现 + P3 单元测试 + P4 viz。
>
> ⚠️ **v2 → v3 关键修订（2026-04-21 上午复盘）**
>
> 1. **删除 `next_likely_actions` 字段** ——原因见 §0.5。LLM 有"偷懒重复"习惯，把"下一步建议"喂回去会反复产出相同的准备性事件而不收尾；P3 里程碑层才是正统的"结构化路径管理"，pursuits 采取**松管理 + 轻量护栏**路线。
> 2. **MA 独占 `estimated_span` / `done_criterion` 修改权** ——MB（日程侧）无法看到对话细节判断延期合理性，只能保留"完成 / 放弃"判断；MA 修改必须带 `evidence_quote` + `evidence_message_ref` 两字段硬校验。
> 3. **引入"角色时间"（character time）** ——离线切换 / 场外挂机会让真实时间流逝但角色生活暂停；用 `schedule_timeline` 扫 gap > 24h 的段视为停顿，`pacing_ratio` / `auto-paused` 判定全部走角色时间。
> 4. **P2-改造-02 轻量护栏双插件** ——注入 `pacing_tag` + `recent_scheduled`（最近 7 天已排过的 pursuit 事件 summary），让 LLM 自觉避免重复；不是硬禁。
> 5. **`progress_log[].ts` 语义对齐** ——MA 写入使用对话 turn 的真实时间戳；MB 写入使用关联 event 的 `start_time`（两者统一视为"角色时间戳"）。
>
> ⚠️ **v3 → v3.1 修订（2026-04-21 晚，closed-loop guard）**
>
> 6. **CS + MA prompt 补"单轮闭环事件不建 pursuit"护栏**（§2.6 / §3.7）。原因：对话/素材里经常出现"提出→当场执行→当场完成"的一次性事件（带饭、查快递、念诗），LLM V1 prompt 会把它们当作 pursuit 建库，产出"僵尸目标"——创建后一直 active，要等 14 天 character time 才被 MB 自动 paused。V0 prompt 有"不是已经做完的事"约束，V1 意外删了，现在补回并升级为带样例的反例表 + 自检问题 (d)。
> 7. **T7a/T7b/T7c 回归测试护住护栏** ——`sandbox/tests/test_pursuits_v3_prompt_guards.py` 9 条断言防止未来重构又把护栏删掉。
>
> ⚠️ **v3.1 → v3.2 修订（2026-04-21 晚 2，DB read 走注入 / CS 补对话入参）**
>
> 8. **工作流节点禁止直接 SQL 查库**：Dify 工作流里 **没有** 执行 SQL 的节点类型；原 v3 把 `CS-01 / MA-01 / MB-01` 写成 `tool → DB read` 是假设存在一个"工具流程薄封装"做 SELECT——这和"中控 source=0 预填 sys.*"的现有实践冲突。**正确做法**：中控在工作流触发前把 `pursuits_library` 从表里查出来作为 `sys.pursuits_library` 注入；工作流内只读这个变量。空判断用 `if-else` 节点做。**写库**仍走工具流程（`pursuits_lib_write`，§7.2 保留），因为写需要事务性语义，工作流 END 透传 payload 由中控收尾也可行，但本版暂保留 tool。
> 9. **CS START 补 `start.raw_records` 入参**：用户 2026-04-21 指出——CS 冷启动时最近一段对话（raw 非摘要）形成的 pursuit 权重应最高；当前 §2.2 只有 lv_1/2/3 / big_event / zip_char_pro，没有 raw chat，mengya 场景实测对话稀少时 lv_1/2/3 也可能为空。§2.2 加 `start.raw_records`；对应 prompt v2（"对话优先"段）挪到 §8 Day 3 落地。

---

## §0 图例与标注法

### 0.1 节点卡片格式

每个节点按如下结构列出：

```
╭────────────────────────────────────────
│ [节点编号] 节点中文标题
│ id:   Nxxxxxxxxxxxxx（占位，导入 Dify 时生成）
│ type: code | tool | variable-extractor | variable-assigner | if-else | aggregator | parameter-extractor
│
│ 入参（测试态 ← fixture）：
│   - varA ← start.fixture_field
│   - varB ← Nyyy.output
│
│ 入参（线上态 ← sys./缓存/DB）：
│   - varA ← sys.user_id
│   - varB ← cache[dim=user_id+member_id][key=lv_1]
│
│ 出参：
│   - field_x: string
│   - field_y: array
│
│ 逻辑伪代码：
│   1. ...
│
│ 为什么这么做（design rationale）：
│   一句到三句话解释该节点的存在理由，特别是"为什么拆到单独节点"
╰────────────────────────────────────────
```

### 0.2 存储层简记

| 简记 | 层 | 读 | 写 | 典型例子 |
|---|---|---|---|---|
| `【DB】` | 持久化（跨天跨会话）| **不由工作流节点直接查**；中控以 `sys.*`（source=0）预填入参注入 | **工作流 END 透传 payload，中控在回调里 upsert** | `pursuits_library`、`character_profile` |
| `【缓存】` | 中短期（5min ~ 7d）| `variable-extractor` 维度+key | `variable-assigner` 维度+key+ttl | `lv_1`、`interact_guide`、`pursuits_top5_cache` |
| `【sys】` | 流程启动预填 | `${sys.xxx}` 全局引用 | 中控管理，流程内不写 | `sys.user_id`、`sys.baji_records_50`、`sys.pursuits_library` |
| `【START】` | 测试期 fixture 入口 | `${start.xxx}` 引用 | —（测试态唯一入口）| `start.fixture_pursuits`、`start.fixture_chat` |
| `【Prompt】` | LLM 节点的 prompt 变量 | 节点内占位符 `{{varname}}` | — | LLM 节点模板 |

> **读 DB 的规范路径**（2026-04-21 晚 2 锁定）：Dify 工作流节点**没有**执行 SQL 的能力。所有"读库然后判空 / 拼字段"类场景必须由中控在触发工作流前查好表，通过 `sys.*`（线上）或 `start.*`（测试态 fixture）注入；工作流内用 `if-else` 或 `code` 节点判空 / 解析。
>
> **写 DB 的规范路径**（2026-04-21 晚 2 锁定，与 P2/P3 统一）：工作流末端由 `code` 节点产出 `new_library` payload，`END` 节点把 payload 输出；中控在 workflow 回调里解析 END 输出并 upsert 到 `pursuits_library` 表。**不保留任何写库工具流程**（原 `pursuits_lib_write` 删除）——和 P2 `schedule_timeline` / P3 `future_plan` 的服务端写入流程完全对齐。**缓存写**（`pursuits_top5_cache` / `uar_daily_counter`）仍走 `variable-assigner` 节点，这与 DB 写无关，不受此规范影响。

### 0.3 节点编号规范

本文件内用 `[CS-01]` / `[MA-03]` / `[MB-05]` / `[P2-改造-01]` / `[BCA-改造-01]` 命名节点，便于 P3 单测和 P4 viz 对应。

### 0.4 角色时间 vs 真实时间（v3 新增关键概念）

- **真实时间（real time）**：系统 wall clock，`sys.current_time` 给的是它。
- **角色时间（character time）**：角色视角下"经过了多少生活时间"。
    - **离线切换关停期间**，角色生活暂停；但 real time 仍在走。
    - **计算方式**：遍历 `schedule_timeline` 按 `start_dt` 排序，凡是相邻事件之间 gap > **24h** 的一段视为"角色时间断档"，在 `days_since_created` 计算时整段减去。
    - 若该 pursuit 创建以来 timeline 完全没 gap（未停机），character time ≡ real time。
- **统一规则**：所有"该 pursuit 创建以来多久了"、"多久没进展"、`pacing_ratio` 分母，一律走 character time。
- **`progress_log[].ts`**：存**角色时间戳**，即：
    - MA 写入：取对话 turn 的真实 `timestamp`（对话本身发生在现实，就是角色时间）。
    - MB 写入：取关联 event 的 `start_time`（schedule_timeline 的时间就是角色时间）。

### 0.5 设计否决记录（v3 重要 context）

| 被否方向 | 否决理由 |
|---|---|
| **`next_likely_actions` 里程碑式路径** | 与 pursuits 的"松目标 + 开放演化"定位冲突；LLM 偷懒习惯会反复复制建议→生成相同准备事件→永不收尾。结构化路径管理由 **P3 里程碑层** 承接。|
| **MB 改 `estimated_span`（延期判断）** | MB 输入只有 schedule_timeline，看不到对话细节；无法判断"延期是合理演化还是路径错误"，改字段等于给 LLM 主观延期开口子。|
| **所有人都能改 `done_criterion`** | 改完成条件等于偷偷降低标准"提前完成"。只允许 MA 改 + 必须带用户/角色在对话中明确表达的 `evidence_quote`。|
| **纯真实时间做 `auto-paused` 判定** | 离线切换期间用户体验上是"暂停"，但真实时间到时仍会误判 2 周无进展。改走角色时间即可避免。|
| **硬禁 LLM 重复推进同一 pursuit** | 过度结构化；改成在 prompt 里透明展示"过去 7 天已排的相关事件"，让 LLM 自觉回避。|
| **单轮闭环事件也建 pursuit**（2026-04-21 补）| V1 prompt 漏了这条约束导致僵尸目标泛滥；现在用反例表 + 自检(d) 明确排除"提出→当场做→当场完成"的一次性事件。|

---

## §0.6 Pursuits 记录 schema（v3 锁定）

> 每条 pursuit 对象：**7 个业务字段 + 5 个元数据字段 + 2 个追踪数组** = 14 字段。

### 业务字段（7，LLM 可见 / 可写）

| 字段 | 类型 | 写入方 | 改动规则 | 用途 |
|---|---|---|---|---|
| `title` | string | CS / MA.new | 新建后不改 | 人类可读目标名，注入 prompt |
| `dimension` | enum(9) | CS / MA.new | 新建后不改 | 分组 / 注入时按 dimension 做多样性 |
| `urgency` | enum(hard/medium/soft) | CS / MA.new | MA 可随 progress 调整 | Top-5 主排序键 |
| `estimated_span` | enum(days_1_3/week_1/weeks_2_4/months_1_3/months_3_12) | CS / MA.new / **MA.update_estimated_span**（带 evidence）| **MA 独占**（MB 禁修）| Top-5 次排序键；`pacing_ratio` 分母 |
| `done_criterion` | string | CS / MA.new / **MA.update_done_criterion**（带 evidence）| **MA 独占**（MB 禁修）| LLM 判完成的依据 |
| `current_stage` | string (≤ 40 字) | CS / MA / MB | 每次 progress 都会改 | 当下推进状态，注入 prompt / top-5 展示 |
| `context_hint` | string (≤ 60 字) | CS / MA.new | 新建后不改 | 背景记忆，帮助 LLM 理解为什么追求它 |

### 元数据字段（5，系统管理）

| 字段 | 类型 | 写入方 | 用途 |
|---|---|---|---|
| `id` | string (pur_NNN) | CS / MA.new | 主键 |
| `status` | enum(active/paused/done/dropped) | CS / MA / MB | 生命周期（创建默认 "active"，CODE 层硬赋值）|
| `created_at` | ISO string | CS / MA.new | 角色时间锚点；`pacing_ratio` 分子起点 |
| `updated_at` | ISO string | 每次改 | last-write-wins 仲裁 |
| `source` | enum(cold_start/conversation/schedule) | CS / MA.new | 诊断用 |

### 追踪数组（2）

| 字段 | 类型 | 写入方 | 元素 schema |
|---|---|---|---|
| `progress_log` | array | MA / MB | `{ ts: ISO, note: string, by: "MA" \| "MB", evidence_ref?: string }` |
| `linked_schedule_events` | array[string] | MB only | event_id 列表，用于"最近 N 天已排"去重 |

**已删除字段**（v2 → v3）：
- ~~`next_likely_actions: array[string]`~~ — 见 §0.5 否决理由

### MA 变更桶（v3 新增 2 桶，共 8 桶）

| 桶 | 说明 | 必填字段 | v2 是否存在 |
|---|---|---|---|
| `progress_updates[]` | 推进 current_stage + 追加 progress_log | pursuit_id, new_stage, evidence_message_ref, evidence_quote | ✅ |
| `completed[]` | status=done | pursuit_id, evidence_message_ref, evidence_quote | ✅ |
| `to_pause[]` | status=paused | pursuit_id, evidence_message_ref, evidence_quote | ✅ |
| `to_revive[]` | status=active | pursuit_id, evidence_message_ref, evidence_quote | ✅ |
| `new_pursuits[]` | 新建 pursuit | title / dimension / urgency / estimated_span / done_criterion / current_stage / context_hint / evidence_message_ref / evidence_quote | ✅（无 evidence）|
| `priority_order[]` | 整体重排 | pursuit_id 有序数组 | ✅ |
| **`update_estimated_span[]`** | 调整时长档位 | pursuit_id, new_span, evidence_message_ref, evidence_quote | 🆕 v3 |
| **`update_done_criterion[]`** | 修订完成条件 | pursuit_id, new_criterion (≤100 字), evidence_message_ref, evidence_quote | 🆕 v3 |

**硬校验（MA-05 节点）**：
- `evidence_message_ref` 必须是本批次对话内的 turn 号 ∈ [1, turn_count]
- `evidence_quote` 必须是 `normalized_turns[evidence_message_ref].content` 的 substring（allow whitespace-normalized）
- 任一失败 → 该变更条目落 `rejected`，其他桶不受影响

### MB 变更桶（v3 缩减为 4 桶）

| 桶 | 说明 | v2 是否存在 |
|---|---|---|
| `progress_updates[]` | 推进 current_stage + 追加 progress_log（ts=event.start_time）| ✅ |
| `completed[]` | status=done（event 完成 = 目标完成时）| ✅ |
| `auto_paused[]` | status=paused（**角色时间 ≥ 14 天无 progress_log 追加**，v3 规则）| 🆕 自动化 |
| `priority_order[]` | 重排 | ✅ |

**MB 被禁桶**：~~`to_revive`（MB 看不到复活信号）、`new_pursuits`（日程不冒新目标）、`update_estimated_span`、`update_done_criterion`~~。

---

## §1 全局总览

| # | 工作流 | 节点数 | LLM 节点 | CODE 节点 | extractor | assigner | tool(DB) | if-else | 触发 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | **Cold-Start** 冷启动 | 6 | 1 | 2 | 0 | 0 | 0 | 1 | 服务端判定库不存在 + 有对话历史，手动触发 1 次 |
| 2 | **M-A** 对话后维护 | 8 | 1 | 4 | 1 | 1 | 0 | 0 | `chat_records_to_lv1_summary` 完 + 5min delay |
| 3 | **M-B** 日程后维护 | 9 | 1 | 4 | 1 | 2 | 0 | 0 | 每日首次 P2 cron 之后 |
| 4 | **P2 future_plan_to_schedule**（改造）| +4 新 & 改 2 原 | prompt +5 段 | +2 新 & 1 原扩 | +1 | +1 | 0 | 0 | 原有 cron，不变 |
| 5 | **baji_chat_all**（改造）| +2 节点 | 不动 | +1 | +1 | 0 | 0 | 0 | 对话每 turn，不变 |

> 所有新 LLM 节点统一 `doubao-1.5 pro 32k`，存量 LLM 节点模型不改。
> 节点数与 v2 一致；v3 的改动大多是**节点内部逻辑 / prompt 内容 / 硬校验规则**变更，拓扑未变。
> **tool(DB) 列 v3.2 全部归零**（2026-04-21 晚 2）：读走 `sys.*` 注入（§0.2 读规范），写走 `END` 透传让中控 upsert（§0.2 写规范）。原计划的 3 个写 tool 节点（CS-05 / MA-07 / MB-07）全删，由前一个 CODE 节点的 `new_library` 直接流到 END；CS/MA/MB 总节点数随之各减 1，CODE/if-else 补上对应位置。与 P2 `schedule_timeline` / P3 `future_plan` 的服务端写入流程完全对齐。

**触发关系图**：

```
  [判定库不存在 + 有历史] ──▶ Cold-Start（只跑 1 次）─┐
                                                      │ write
  [对话记录 lv1 落盘] ──▶ M-A（每次对话结束）────────┤  【DB pursuits_library】
                                                      │
  [每日首次 P2 cron] ──▶ M-B（每日 1 次）─────────────┤  write + write pursuits_top5_cache【缓存】
                                                      │
  P2 future_plan_to_schedule（每 2h cron）──读────────┘
       │ 注入 top5 + UAR 判定
       ▼ 生成 schedule_timeline【DB】
  baji_chat_all（每 turn）──读────── schedule_timeline
       │ 注入 UAR 回调消息
       ▼ 对话 LLM
```

---

## §2 工作流 #1：Cold-Start（冷启动）

### 2.1 流程目标

已有对话历史的角色首次建库，一次性从 `lv1 / lv2 / lv3 / big_event / zip_char_pro` 抽 10-15 条 pursuit 写入 `pursuits_library`【DB】。

**v3 变化**：CS 不再产出 `next_likely_actions`；prompt 里把该字段整段删掉，输出 JSON schema 只留 7 业务字段。

### 2.2 START 节点测试数据入口

**测试态 fixture**：`sandbox/fixtures/pursuits/mengya__test_user.json`（已存在）+ 各层 memory fixture（目前沙盒从 `progress` 目录读）。

**测试态 START 变量声明**（Dify 导入时 `data.variables[]`）：

| 变量名 | 类型 | 测试态来源 | 线上态来源 |
|---|---|---|---|
| `start.char_id` | string | "mengya" | `sys.member_id` |
| `start.user_id` | string | "test_user" | `sys.user_id` |
| `start.zip_char_pro` | string | fixture.zip_char_pro | `sys.character_profile` |
| `start.npc_status` | string | fixture.npc_status | `sys.npc_status` |
| `start.usr_prof` | string | fixture.usr_prof | `sys.usr_profile` |
| `start.big_event` | string（截 30k）| fixture.big_event | `sys.big_event` |
| `start.lv_1` | string | fixture.lv_1 | `sys.message_summary_1` |
| `start.lv_2` | string | fixture.lv_2 | `sys.message_summary_2` |
| `start.lv_3` | string | fixture.lv_3 | `sys.message_summary_3` |
| `start.interact_guide` | string | fixture.interact_guide | `sys.current_interaction_intensity` |
| **`start.raw_records`** | **string** | **fixture.raw_baji_records_50（或测试 fixture 给的最近 50 轮原始对话 JSON）** | **`sys.baji_records_50`** |
| **`start.pursuits_library`** | **string（可为空串/`"null"`）** | **fixture 无时传空串** | **`sys.pursuits_library`**（中控 source=0 从 `pursuits_library` 表查；**库不存在时注入空串或 `null`**）|

> 关于 start.* 各字段的真实 schema 与样例见 `pursuits_input_contract_v1.md` §2。
>
> **`start.raw_records`（2026-04-21 晚 2 补）**：CS 冷启动时，最近一段 raw 对话形成的 pursuit 权重应高于摘要层；lv_1/2/3 是分层摘要，可能在新账号对话稀少时为空（mengya 实测），raw_records 是兜底+优先信号。prompt v2 使用方式见 §8 Day 3 TODO。
>
> **`start.pursuits_library`（2026-04-21 晚 2 补）**：工作流节点不能直接跑 SQL，所以 CS-01 判空逻辑由中控预查 + 注入 `sys.pursuits_library` + 工作流内 `if-else` 判空完成（详见 §2.4 CS-01 节点）。**库不存在时中控必须注入空串或 `null`**，否则 CS-01 if-else 无法判空。

### 2.3 节点链

```
[CS-00 START]
    ↓
[CS-01 判定库是否为空] (if-else on ${sys.pursuits_library}) ─┬─ 非空 → [CS-END-skip]
                                                             └─ 空
    ↓
[CS-02 数据预处理（big_event 截断 + 分层记忆精简 + raw_records 精简）] (code)
    ↓
[CS-03 LLM 抽取 pursuits] (tool → doubao-1.5 pro 32k)
    ↓
[CS-04 规范化 + 去重 + 组装 new_library] (code)
    ↓
[CS-END-ok]  ← output { new_library, accepted_count }，中控回调写 pursuits_library 表
```

> **v3.2 改动**：
> 1. CS-01 由原 `tool(SQL SELECT 1)` 改为 `if-else` 节点，判的是中控已注入的 `sys.pursuits_library` 是否空串/`null`。原 CS-01b 独立 if-else 节点合并消失。
> 2. **原 CS-05 写库 tool 节点删除**（2026-04-21 晚 2 第二次修订）：CS-04 直接流到 CS-END-ok；CS-END-ok 的 output 字段带 `new_library` payload，中控在 workflow 回调里把 payload 写入 `pursuits_library` 表——与 P2 `schedule_timeline` / P3 `future_plan` 的服务端写入流程一致。节点总数从 7 减到 6（与 §1 全局表对齐）。

### 2.4 节点详表

```
╭─── [CS-00 START] ────────────────────────
│ type: start
│ 入参: 见 §2.2 START 变量声明表
│ 出参: 无（sys.*/start.* 全局可引）
╰──────────────────────────────────────────
```

```
╭─── [CS-01 判定库是否为空] ────────────────
│ id: Nxxx01
│ type: if-else                          # v3.2 由 tool(SQL) 改为 if-else
│
│ 入参（测试/线上同）:
│   - lib ← ${sys.pursuits_library}      # 中控 source=0 预填；库不存在注入 "" 或 "null"
│
│ cases:
│   - id: "exists"
│     condition: lib != "" AND lib != "null" AND lib != null
│
│ exists 分支 → [CS-END-skip]（流程结束，不重建库）
│ else 分支   → [CS-02]
│
│ 为什么这么做（v3.2）:
│   Dify 工作流节点没有执行 SQL 的能力；原设计的 `pursuits_lib_exists` 工具
│   流程与"中控 source=0 预填 sys.*"的现有实践冲突。正确做法是把 DB 查库
│   交给中控——触发 CS 前中控已经从 pursuits_library 表查过一次（这是 CS
│   的触发条件本身："服务端判定库不存在 + 有对话历史"）——把结果作为
│   sys.pursuits_library 注入，工作流只做 defensive 空判。
│
│   **defensive 仍必要**：即使服务端触发条件说"库不存在"，理论上并发场景
│   下另一条 CS 请求可能先写入；空判兜底避免重复建库覆盖已有数据。
╰──────────────────────────────────────────
```

```
╭─── [CS-02 数据预处理] ────────────────────
│ id: Nxxx02
│ type: code
│ code_language: javascript
│
│ 职责：对 prompt 里无法用 `${}` 内嵌语法处理的字段做 JS 预处理；
│       **不负责拼 prompt 模板**（模板直接塞在下游 LLM 节点的
│       data.variables[prompt].value 里，按线上 mode B 惯例）
│
│ 入参 variables:
│   - big_event ← ${start.big_event}         # 可能超 30k 字符，需硬截
│   - lv_1 ← ${start.lv_1}                    # JSON 数组字符串
│   - lv_2 ← ${start.lv_2}
│   - lv_3 ← ${start.lv_3}
│   - raw_records ← ${start.raw_records}      # v3.2: 最近 50 轮原始对话 JSON
│
│ 出参:
│   - big_event_trimmed: string              # 硬截 30k 字符后的 big_event
│   - lv_1_digest: string                    # 精简后的纯文本段落
│   - lv_2_digest: string
│   - lv_3_digest: string
│   - recent_chat_digest: string             # v3.2: raw_records 过滤伪消息后的纯文本段
│
│ 逻辑:
│   1. big_event.substring(0, 30000) → big_event_trimmed
│   2. JSON.parse(lv_N) → 拼成 "- xxx\n- yyy" 文本段 → lv_N_digest
│   3. JSON.parse(raw_records) → 过滤伪消息（is_fake/system_prompt 类）→
│      取最近 N 轮（建议 20-30）→ 拼 "[speaker] content" 文本段 →
│      recent_chat_digest（为空时给占位 "(无近期对话)"）
│   4. return { big_event_trimmed, lv_1_digest, lv_2_digest, lv_3_digest,
│               recent_chat_digest }
│
│ 不需要预处理的字段（zip_char_pro / npc_status / usr_prof / interact_guide
│ / char_id / user_id）直接让下游 LLM 节点用 ${start.xxx} 内嵌引用即可，
│ 不走这个 code 节点。
│
│ v3.2 新增：raw_records 精简复用 MA-02/MA-03 的伪消息过滤逻辑，
│            避免系统消息污染 CS 抽取结果；prompt v2 会在 §8 Day 3 补"对话优先"段
│            使 LLM 把 recent_chat 中提到的 pursuit 放前面。
│
│ 沙盒对应: pursuits_cold_start.load_test_data() 的字段切片逻辑 +
│           pursuits_maintain_after_chat._normalize_turns 的伪消息过滤
╰──────────────────────────────────────────
```

```
╭─── [CS-03 LLM 抽取 pursuits]  ────────────
│ id: Nxxx03
│ type: tool (doubao-1.5 pro 32k)
│ tool_version: 1.0.0
│ async_enabled: false
│ temperature: 1.0
│
│ 入参 variables（Dify mode B：prompt 作为字面量直接存在节点上）:
│   - prompt (variable_type=string, value=<整段 cold_start 系统 prompt 模板>)
│       模板内嵌引用：
│         ${start.char_id} / ${start.user_id}
│         ${start.zip_char_pro} / ${start.npc_status} / ${start.usr_prof}
│         ${Nxxx02.big_event_trimmed}
│         ${Nxxx02.lv_1_digest} / ${Nxxx02.lv_2_digest} / ${Nxxx02.lv_3_digest}
│         ${Nxxx02.recent_chat_digest}      # v3.2 新增，对应 prompt v2 "对话优先"段
│         ${start.interact_guide}
│   - user_input (variable_type=string, value="Output JSON array only.")
│
│ 出参:
│   - output: string（LLM plaintext，含 JSON array of pursuit）
│
│ 变化（v3）：
│   - prompt 模板删除 next_likely_actions 字段；输出 schema 改为：
│       [{ "title", "dimension", "urgency",
│          "estimated_span", "done_criterion",
│          "current_stage", "context_hint" }]
│     共 7 字段，其余（id/status/created_at/...）由 CS-04 补。
│   - **2026-04-21 晚**：prompt 的"❌ 不是 pursuit"反例表新增 2 条"单轮闭环"
│     样例；"质量要求"自检清单从 3 条扩到 4 条（补 (d) 到素材结束时是否已 done）。
│     详见 §2.6。
│
│ Prompt 模板来源：sandbox/tools/pursuits_coldstart_probe.py::COLD_START_PROMPT_V1
│ Prompt chars ≈ 5400（含占位符）；真实运行时展开约 10-30k 字符。
│
│ 为什么这么做：
│   next_likely_actions 是"里程碑式路径"的残留；pursuits 定位为松目标，
│   该字段一存在就会被 P2 当事件生成锚点反复使用，引发 LLM 偷懒重复。
│   P3 里程碑层才承担结构化路径。
│
│ 沙盒对应: pursuits_cold_start.extract_pursuits_v1() 的 LLM call
╰──────────────────────────────────────────
```

```
╭─── [CS-04 规范化 + 去重 + 组装 new_library] ─
│ id: Nxxx04
│ type: code
│
│ 入参 variables:
│   - raw ← ${Nxxx03.output}
│   - char_id ← ${start.char_id}
│   - user_id ← ${start.user_id}
│
│ 出参:
│   - accepted: array         # 合法 pursuit 对象数组
│   - rejected: array         # 含 _reject_reason 的丢弃项
│   - accepted_count: number
│   - new_library: string     # v3.2 新增，JSON.stringify 后的 DB payload，交给 CS-END-ok
│
│ 逻辑（v3.2）:
│   1. JSON.parse(raw) → list
│   2. 每条补元数据：id、**status="active" (硬编码)**、created_at=now、updated_at=now,
│      source="cold_start"、progress_log=[]、linked_schedule_events=[]
│   3. 7 业务字段完整性校验（缺任一 → 进 rejected）
│   4. dimension 归一到 9 维
│   5. Jaccard ≥ 0.8 两两合并
│   6. 组装 payload = { char_id, user_id, pursuits: accepted, updated_at: now }
│   7. new_library = JSON.stringify(payload)
│   8. return { accepted, rejected, accepted_count, new_library }
│
│ 为什么这么做：
│   **规范化放在 LLM 之后、写库之前**，让 LLM 只关心业务 7 字段，
│   工程元数据（id/ts/state）由代码注入，不占 LLM token，也避免
│   LLM 自由发挥写错 id 格式或 ISO 时间格式。status 固定 "active" 也
│   是这个逻辑——LLM 无需也不能决定初始状态。
│
│   v3.2 合并"组装 new_library"职责：原由 CS-05 tool 节点做 payload 组装 +
│   SQL INSERT；现在 tool 节点删除，组装职责落在 CS-04 末尾，payload 直接
│   流向 END。与 P2 `future_plan_to_schedule` 末节点把 schedule_timeline
│   序列化后交给 END 的写法完全对齐。
╰──────────────────────────────────────────
```

> **原 CS-05 写库 tool 节点已于 2026-04-21 晚 2 删除**——参见 §0.2 写规范 / §2.3 节点链说明 / §9 diff 表。CS-04 节点额外负责"组装 new_library"，即在 accepted 基础上包装为 DB payload 结构（`{ char_id, user_id, pursuits: [...], updated_at }`），直接交给 CS-END-ok 输出。

```
╭─── [CS-END-ok] ──────────────────────────
│ type: end
│
│ output:
│   - new_library ← ${Nxxx04.new_library}      # v3.2 新增，中控回调 upsert
│   - accepted_count ← ${Nxxx04.accepted_count}
│
│ 中控职责（§7.6）:
│   收到 CS-END-ok 输出后 INSERT INTO pursuits_library(char_id, user_id,
│   pursuits_json, updated_at) VALUES(?, ?, new_library, now())
╰──────────────────────────────────────────
```

```
╭─── [CS-END-skip] ────────────────────────
│ type: end
│
│ output:
│   - skipped: true
│   - reason: "library already exists"
│
│ 中控职责: 收到 skipped=true 直接不做 DB 写，记日志即可
╰──────────────────────────────────────────
```

### 2.5 数据链测试（P3）

| 单测 | 输入 fixture | 校验点 |
|---|---|---|
| ut-cs-01 | `sys.pursuits_library` 非空（注入已有 payload）→ CS-01 if-else 真分支 | END-skip 命中，不进 CS-02 |
| ut-cs-02 | `sys.pursuits_library=""` + 有对话历史 → 走全链 | CS-04.accepted_count ∈ [10, 15] |
| ut-cs-03 | 故意造 LLM 输出非 JSON | CS-04.accepted_count=0，rejected 全量 |
| **ut-cs-04 (T1)** | 构造 LLM 输出含多余 `next_likely_actions` 字段 | CS-04.accepted 中该字段被剔除，校验不因多字段失败（容错）|
| **ut-cs-05 (T7a)** | prompt-level guard 断言 | `COLD_START_PROMPT_V1` 含"在素材里已经当场闭环"、四个自检问题 (a)-(d)、两条闭环样例行 |
| **ut-cs-06 (T8a)** | CS-02 对 `start.raw_records` 做伪消息过滤 | 输入含 `{is_fake:true}` / system_prompt 的 records 被剔除；`recent_chat_digest` 只含真实 speaker/content；为空对话时给占位"(无近期对话)" |
| **ut-cs-07 (T8b)** | `sys.pursuits_library=null` 兜底判空 | CS-01 if-else else 分支命中（与 `""` 一样走 CS-02）|

### 2.6 Closed-loop guard（2026-04-21 晚补）

**问题起源**：V0 prompt 的 ❌ 反例表里有"已经做完的事"一行，V1 重构 prompt 时把它删了没人注意，导致 LLM 在素材里看到"提出→执行→完成"的一次性事件也会建成 pursuit；创建后状态 active，只能等 MB 角色时间 14 天阈值 auto_paused——僵尸目标。

**修订点**：

1. **❌ 反例表新增 2 行**（`pursuits_coldstart_probe.py::COLD_START_PROMPT_V1`）：

   | 看起来像，实际不是 | 为什么不是 | 该归到哪 |
   |---|---|---|
   | **"给用户带了份饭送到了"** | **在素材里已经当场闭环**（提出→执行→完成都发生了）；这是一次**事件级完成**，不是需要未来多步推进的目标 | **不入库** |
   | **"答应了用户带礼物，已送达"** | 同上，素材里已经 done 了 | **不入库** |

2. **自检清单从 3 条扩到 4 条**，补第 (d) 条：
   - (d) **到素材（big_event / lv_1 / lv_2 / lv_3 / 对话）结束时，这件事是不是已经达到 done_criterion 了？如果是，删掉——它是事件级完成，不是需要未来多步推进的 pursuit。**

3. **回归测试**：`sandbox/tests/test_pursuits_v3_prompt_guards.py` 里 `test_T7a*` 系列 4 条断言，防止未来重构又把护栏删掉。

**与 MA 的 §3.7 guard 对应**：这里看的是 big_event / lv_1/2/3 素材；MA 看的是 raw chat turns。两边约束一致，只是判断依据不同。

---

## §3 工作流 #2：M-A（对话后维护）

### 3.1 流程目标

对话结束 + 5min delay 后，读 `pursuits_library`【DB】 + `baji_records_50`【sys】，LLM 判 **8 类变更**（v3 从 6 桶扩到 8 桶），更新库，重建 top-5 快照写入【缓存 pursuits_top5_cache】。

**v3 关键变化**：
1. 8 桶（新增 `update_estimated_span` / `update_done_criterion`）。
2. 所有可能"主观偏移"的桶（progress / completed / pause / revive / update_*）**必须带 `evidence_message_ref` + `evidence_quote`**，MA-05 硬校验。
3. **2026-04-21 晚**：§5 new_pursuits 补"单轮闭环反例"（见 §3.7）。

### 3.2 START 节点测试数据入口

**测试态 fixture**：
- 对话：`sandbox/fixtures/chats/mengya_test_user_20260421__pseudoheavy.json`（或其他 M-A fixture）
- pursuits：`sandbox/fixtures/pursuits/mengya__test_user.json`

**START 变量**：

| 变量名 | 测试态来源 | 线上态来源 |
|---|---|---|
| `start.char_id` | "mengya" | `sys.member_id` |
| `start.user_id` | "test_user" | `sys.user_id` |
| `start.baji_records_50` | fixture.raw_baji_records_50 | `sys.baji_records_50` |
| `start.session_ended_at` | fixture.ended_at | `sys.current_time` |
| **`start.pursuits_library`** | **fixture 整个 payload JSON 字符串** | **`sys.pursuits_library`**（中控 source=0 从 `pursuits_library` 表查注入）|

> baji_records_50 真实 schema + 伪消息语义见 `pursuits_input_contract_v1.md` §3。
>
> **`start.pursuits_library`（2026-04-21 晚 2 补）**：MA 读库不再走 tool 节点跑 SQL，而是中控在触发 MA 前查好表注入为 sys.*，MA-01 只做 JSON parse + count。原 `tool_key=pursuits_lib_read` 从 §7.2 删除。

### 3.3 节点链

```
[MA-00 START]
    ↓
[MA-01 解析 pursuits_library 注入] (code)    ← v3.2 由 tool 改为 code
    ↓
[MA-02 规范化对话+过滤伪消息] (code)
    ↓
[MA-03 对话预处理（反解 baji_records + 过滤伪消息 + 精简 pursuits library）] (code)
    ↓
[MA-04 LLM 判定变更] (tool → doubao-1.5 pro 32k)
    ↓
[MA-05 解析 + 硬校验（含 evidence 校验）] (code)
    ↓
[MA-06 应用变更 + 重建 top-5 + 组装 new_library] (code)
    ↓
[MA-08 写 top-5 缓存] (variable-assigner)   ← v3.2 原 MA-07 写库 tool 删除，MA-06 直接到 MA-08
    ↓
[MA-END]  ← output { new_library, accepted_count, diff_summary }，中控回调 upsert
```

### 3.4 节点详表

```
╭─── [MA-00 START] ────────────────────────
│ type: start
│ 入参: 见 §3.2
╰──────────────────────────────────────────
```

```
╭─── [MA-01 解析 pursuits_library 注入] ───
│ id: Nmaxx01
│ type: code                            # v3.2 由 tool 改为 code
│ code_language: javascript
│
│ 入参:
│   - lib_raw ← ${start.pursuits_library}   # 测试态 fixture；线上 sys.pursuits_library
│
│ 出参:
│   - library: string（JSON 串，整个 library payload，透传给下游）
│   - active_count: number
│   - paused_count: number
│
│ 逻辑:
│   1. lib = JSON.parse(lib_raw || "{}")
│   2. pursuits = lib.pursuits || []
│   3. active_count = pursuits.filter(p => p.status === "active").length
│   4. paused_count = pursuits.filter(p => p.status === "paused").length
│   5. return { library: lib_raw, active_count, paused_count }
│
│ 为什么这么做（v3.2）:
│   Dify 工作流节点没有 SQL 能力；MA 的 DB 读走"中控 source=0 预填 sys.*"
│   的通用路径（和 sys.baji_records_50 / sys.schedule_timeline 一致）。
│   active/paused 计数很轻量，放 code 节点里不用再起一跳 tool。
│
│ 沙盒对应: pursuits_maintain_after_chat._count_pursuits_by_status
╰──────────────────────────────────────────
```

```
╭─── [MA-02 规范化对话+过滤伪消息] ─────────
│ id: Nmaxx02
│ type: code
│
│ 入参 variables:
│   - raw_records ← ${start.baji_records_50}
│
│ 出参:
│   - normalized_turns_json: string（JSON.stringify(array of {turn, role, content, ts})）
│   - turn_count: number
│
│ 逻辑（对应 chat_adapter.describe_pseudo + normalize_chat）:
│   1. 遍历 baji_records_50 每对（assistant, user）
│   2. memberType==0 / signature ∈ {schedule_update, schedulerStartTime,
│      greeting_kickoff} 的 user 侧 → describe_pseudo()
│   3. 按 timestamp 升序编号 turn (1-based)
│   4. 每个 turn 产出 { turn:int, role:"user"|"assistant", content:string,
│      ts:"YYYY-MM-DD HH:MM:SS" }
│   5. return { normalized_turns_json, turn_count }
│
│ 为什么这么做：
│   - 伪消息（cron 推入的调度同步信息）不是真实用户发言，喂给 LLM
│     会让它把"系统消息内容"当成用户意图，造成严重误判。
│   - ts 保留是为了 MA-06 写 progress_log 时用作"角色时间戳"（对话
│     发生在现实 → 对话时间 = 角色时间）。
│   - 输出 JSON 而不是拼好文本，是因为 MA-05 做 evidence_quote 校验
│     时需要原始 content 做 substring 比对。
╰──────────────────────────────────────────
```

```
╭─── [MA-03 对话预处理] ────────────────────
│ id: Nmaxx03
│ type: code
│
│ 入参:
│   - library ← ${Nmaxx01.library}
│   - normalized_turns_json ← ${Nmaxx02.normalized_turns_json}
│
│ 出参:
│   - active_pursuits_digest: string
│   - paused_pursuits_digest: string
│   - normalized_turns_text: string   # "[1] user: ...\n[2] assistant: ..."
│
│ 逻辑（v3）:
│   1. JSON.parse(library) → lib
│   2. lib.pursuits 按 status=active 过滤，拼成多行：
│      "- {id} [{urgency}] {title} | 档位:{estimated_span}
│       | 当下:{current_stage} | 完成条件:{done_criterion}"
│      （注意：不再输出 next_likely_actions）
│   3. paused 同上
│   4. normalized_turns_json → 拼 "[turn] role: content" 文本块
│   5. return {...}
│
│ 为什么这么做：
│   - 把 library JSON 变文本段是因为 Dify LLM 节点的 prompt 接字符串
│     友好度远高于接 JSON（LLM 不擅长解嵌套）。
│   - digest 里显式带 done_criterion 是为了让 LLM 判 completed 时
│     对照条件，而不是主观觉得"差不多了"。
╰──────────────────────────────────────────
```

```
╭─── [MA-04 LLM 判定变更] ──────────────────
│ id: Nmaxx04
│ type: tool (doubao-1.5 pro 32k)
│ temperature: 0.3
│
│ 入参 variables（Dify mode B）:
│   - prompt (string, value=<MA prompt v3 模板>)
│       模板内嵌引用:
│         ${start.char_id} / ${start.user_id}
│         ${Nmaxx03.active_pursuits_digest}
│         ${Nmaxx03.paused_pursuits_digest}
│         ${Nmaxx03.normalized_turns_text}
│         ${sys.current_time}
│   - user_input (string, value="Output JSON only, strictly follow 8-bucket schema.")
│
│ v3 Prompt 主要变化：
│   1. 输出 schema 删除 "next_likely_actions"
│   2. 新增 2 个变更桶:
│      - update_estimated_span[]:
│          { pursuit_id, new_span, evidence_message_ref, evidence_quote }
│        只允许以下触发情境（prompt 强约束）：
│        a. 用户/角色明确说了新的时间预期（"下周搞定"）
│        b. 剧情出现重大延迟信号（"项目被砍了"）
│      - update_done_criterion[]:
│          { pursuit_id, new_criterion (≤100 字),
│            evidence_message_ref, evidence_quote }
│        仅在完成条件明显描述错误或对话里出现明确修订时触发。
│   3. 所有"状态性"桶 (progress / completed / pause / revive / update_*)
│      强制要求 evidence_message_ref + evidence_quote；
│      prompt 里给出 "bad examples" 示例（没原文引用就修改）让 LLM 规避。
│   4. new_pursuits 不需要 evidence_quote（是创造性动作不是修改），
│      但需要 evidence_message_ref 指向触发该 new 的 turn。
│      **2026-04-21 晚**：new_pursuits 段额外补"单轮闭环反例"块（§3.7）
│   5. priority_order 不需要 evidence。
│
│ 为什么这么做：
│   - 最早的设计允许 LLM 主观 progress，实测发现 LLM 会凭"感觉"乱动
│     状态；加 evidence_quote 后 LLM 必须从对话里"抄"出原话，无话
│     可抄时只能放弃，相当于硬门槛。
│   - update_estimated_span / update_done_criterion 是 v3 新增的"延期
│     和完成条件修订"闸门——MB 完全禁修；MA 改必须带证据。这样
│     pursuits 不会被 LLM 静默"缩减目标 → 提前完成"。
│
│ Prompt 模板来源：sandbox/tools/pursuits_maintain_after_chat.py::MAINTAIN_PROMPT
╰──────────────────────────────────────────
```

```
╭─── [MA-05 解析 + 硬校验] ─────────────────
│ id: Nmaxx05
│ type: code
│
│ 入参:
│   - raw ← ${Nmaxx04.output}
│   - library ← ${Nmaxx01.library}
│   - normalized_turns_json ← ${Nmaxx02.normalized_turns_json}
│   - turn_count ← ${Nmaxx02.turn_count}
│
│ 出参:
│   - decision: string（合法化后 JSON 串）
│   - ok: boolean
│   - errors: array       # [{bucket, index, reason}]
│   - rejected: array     # 被 evidence 校验驳回的单项
│
│ 逻辑（v3 核心改动）：
│   1. JSON.parse(raw) → dec
│   2. 对每个桶内每条:
│      a. pursuit_id 必须在 lib.pursuits 里（new_pursuits 除外）
│      b. evidence_message_ref 必须 ∈ [1, turn_count]
│      c. evidence_quote 必须是 normalized_turns[ref-1].content 的
│         substring（allow whitespace-normalized，例 "\n\t" 折成 " "）
│      d. update_estimated_span.new_span 必须 ∈ 5 档枚举
│      e. update_done_criterion.new_criterion length ≤ 100
│   3. 互斥检查：同 pid 不能同时 progress 和 pause；
│      不能同时 update_estimated_span 和 completed；
│      不能 revive 一个不在 paused 状态的 pid
│   4. 违规单项 → rejected.push；桶里保留合规的其余
│   5. 任一桶整体失败（JSON 结构坏）→ ok=false + 桶清空
│   6. return { decision: JSON.stringify(dec), ok, errors, rejected }
│
│ 为什么这么做：
│   - evidence_quote 校验放到 CODE 而不是 LLM 自查——LLM 自查不可靠；
│     CODE 做 substring 是 100% 确定性的硬门槛。
│   - 单项驳回而不是整体 reject，是为了保留"部分可信"的输出；某条
│     瞎编 evidence 不影响其他正常变更。
│   - parameter-extractor 做不到"逐条校验 + 交叉字段关系"，只能 code。
╰──────────────────────────────────────────
```

```
╭─── [MA-06 应用变更 + 重建 top-5 + 组装 new_library] ─
│ id: Nmaxx06
│ type: code
│
│ 入参:
│   - library ← ${Nmaxx01.library}
│   - decision ← ${Nmaxx05.decision}
│   - normalized_turns_json ← ${Nmaxx02.normalized_turns_json}
│   - char_id ← ${start.char_id}               # v3.2: 组装 payload 需要
│   - user_id ← ${start.user_id}
│
│ 出参:
│   - new_library: string        # JSON.stringify({char_id, user_id, pursuits, updated_at})，交给 MA-END
│   - top5_cache: string         # 只含 7 业务字段 + id + progress_log tail 1
│   - diff_summary: string
│   - accepted_count: number     # v3.2: 透传给 MA-END，供中控日志
│
│ 逻辑（v3）:
│   1. lib = JSON.parse(library)
│   2. turns = JSON.parse(normalized_turns_json)
│   3. 按桶顺序应用：
│      a. progress_updates →
│         pursuits[pid].current_stage = new_stage
│         pursuits[pid].progress_log.push({
│             ts: turns[ref-1].ts,              # v3: 对话 turn 的时间
│             note: evidence_quote,
│             by: "MA",
│             evidence_ref: `turn:${ref}`
│         })
│      b. completed → status="done"; progress_log.push(...)
│      c. to_pause → status="paused"; progress_log.push(...)
│      d. to_revive → status="active"; progress_log.push(...)
│      e. new_pursuits → lib.pursuits.push({...补元数据...，status="active"硬编码})
│      f. update_estimated_span → pursuits[pid].estimated_span = new_span
│         progress_log.push({ ts, note:"[span 调整] "+new_span, by:"MA", evidence_ref })
│      g. update_done_criterion → pursuits[pid].done_criterion = new_criterion
│         progress_log.push({ ts, note:"[criterion 修订]", by:"MA", evidence_ref })
│      h. priority_order → 按 pursuit_id 数组在 lib.pursuits 里排序
│   4. 每条变更 updated_at = now
│   5. top-5 构造:
│      - 从 active pursuits 里按 (urgency tier, estimated_span tier) 排
│      - 取前 5
│      - 每条只保留: id, title, urgency, estimated_span, current_stage,
│        done_criterion, context_hint, last_progress_note
│   6. return {...}
│
│ 为什么这么做：
│   - progress_log.ts 用对话 turn 时间戳（不是 now）是为了"角色时间"
│     一致——MA 处理的是发生过的对话，ts 应该是对话实际发生时。
│   - top-5 裁字段是为了 P2 prompt 注入大小可控（5 条 × 几十字）。
│   - 不再含 next_likely_actions——P2 的 LAYER3 文本生成也不会再
│     引用这个字段（见 §5 P2-改造-02 伪代码）。
╰──────────────────────────────────────────
```

> **原 MA-07 写库 tool 节点已于 2026-04-21 晚 2 删除**——参见 §0.2 写规范 / §3.3 节点链说明。MA-06 负责"应用变更 + 重建 top-5 + 组装 new_library"（`new_library = JSON.stringify({ char_id, user_id, pursuits, updated_at })`），payload 直接流向 MA-END。MA-08 写缓存并行，不受影响。

```
╭─── [MA-08 写 top-5 缓存] ─────────────────
│ id: Nmaxx08
│ type: variable-assigner
│
│ 维度: user_id + member_id
│ key:  pursuits_top5_cache
│ ttl:  [23, 59, 59]                    # 24h（下次 M-B 会覆盖）
│ write_mode: over-write
│
│ 入参:
│   - 值 ← ${Nmaxx06.top5_cache}
│
│ 出参: 写入成功
╰──────────────────────────────────────────
```

```
╭─── [MA-END] ──────────────────────────────
│ type: end
│
│ output:
│   - new_library ← ${Nmaxx06.new_library}      # v3.2: 中控回调 upsert
│   - accepted_count ← ${Nmaxx06.accepted_count}
│   - diff_summary ← ${Nmaxx06.diff_summary}
│
│ 中控职责（§7.6）:
│   UPDATE pursuits_library SET pursuits_json=new_library, updated_at=now()
│   WHERE char_id=? AND user_id=?
│   （或用 INSERT ... ON CONFLICT DO UPDATE，与 schedule_timeline 写入一致）
╰──────────────────────────────────────────
```

### 3.5 关键拆分说明（v3）

v3 把 MA-06 继续保留为单 code 节点（不拆 8 桶 = 8 节点）——单节点内**纯计算复合**是允许的（cheatsheet §3.1 不约束）。拆 8 个 if-else + assigner 反而过度工程化。

### 3.6 数据链测试（P3）

| 单测 | 输入 fixture | 校验点 |
|---|---|---|
| ut-ma-01 | pseudoheavy chat + library baseline | MA-05.ok=true / MA-06.top5_cache 含 5 条 |
| ut-ma-02 | chitchat（空信号）| 8 桶全 0，priority_order 按既有 active 排 |
| ut-ma-03 | raw baseline（4 类变更同现）| progress=2, pause=1, new=1, top-5 #1 是 new |
| **ut-ma-04 (T5a)** | 构造 LLM 输出 evidence_quote 对不上 turn 原文 | MA-05.rejected 含该条，其他桶保留；ok=true |
| **ut-ma-05 (T5b)** | 构造 LLM 输出 update_estimated_span new_span="forever" | MA-05.rejected 含该条（枚举不匹配）|
| **ut-ma-06 (T5c)** | 构造对话含"我下周搞定"+ LLM 输出 update_estimated_span days_1_3 | MA-06.new_library 对应 pursuit span 改为 days_1_3 |
| **ut-ma-07 (T7b)** | prompt-level guard | `MAINTAIN_PROMPT` 含"单轮闭环反例"块 + "今晚给我带饭" 等样例 |
| **ut-ma-08 (T7b-pos)** | prompt-level guard（正面对照）| `MAINTAIN_PROMPT` 同时保留"下周陪我去拜访" 类正例，避免矫枉过正 |

### 3.7 Closed-loop guard（2026-04-21 晚补）

**问题起源**：MA 的 §5 new_pursuits 条件只有一句"这是一件明确的、有推进动作的事"。实测 LLM 会把"用户让角色今晚带饭 → 角色回'已送到' → 用户'收到谢谢'"这种**在一轮对话里就走完了"提出→执行→完成"闭环**的事件当作 pursuit 建库——僵尸目标，要等 14 天角色时间 auto_paused。

**修订点**（`pursuits_maintain_after_chat.py::MAINTAIN_PROMPT` §5）：

在 new_pursuits 条件列表末尾追加：

```
- ⚠️ **单轮闭环反例（严格排除）**：
  - 如果一件事**在本次对话内部**就完成了"提出→执行→完成"的整条链路，**不要**建 new_pursuit。
  - 典型样例：
    - ❌ 用户让角色"今晚给我带饭"→ 角色回"已送到你门口"→ 用户回"收到谢谢"：
         这是一次**事件级完成**，不是需要未来多步推进的目标。
    - ❌ 用户说"帮我查下快递"→ 角色查到告诉用户 → 用户说"知道了"：当场闭环，不入库。
    - ❌ 用户让角色"念首诗"→ 角色念了 → 用户"好听"：当场闭环，不入库。
  - 判定标准：**到 transcript 结束时，如果这件事已经达到 done_criterion，就不应该建它。**
    只有还需要未来动作推进的，才是 pursuit。
  - ✅ 反例之反例（这些要建）：
    - 用户"下周陪我去拜访蔡徐坤" → 角色答应（对话里还没去）：建 new_pursuit，done=拜访完成。
    - 用户"周末一起布置新家" → 角色答应（对话里还没做）：建 new_pursuit。
```

**回归测试**：`test_pursuits_v3_prompt_guards.py` 里 `test_T7b*` 系列 4 条断言（含 `test_T7b3` "反例之反例"正面对照检查，防止过度抑制）。

---

## §4 工作流 #3：M-B（日程后维护）

### 4.1 流程目标

每日首次 P2 cron 之后，读 `pursuits_library`【DB】 + 最近 24h `schedule_timeline`【DB】，LLM 判 **3 桶变更**（progress / completed / priority_reorder）+ **code 自动触发的 auto_paused**，更新库，重建 top-5 快照**回写【缓存】**供 P2 runtime 读。

**v3 关键变化**：
1. **MB 禁改 `estimated_span` / `done_criterion`**（见 §0.5 否决理由）。
2. **`auto_paused` 走角色时间**：扫 schedule_timeline 算每个 pursuit 的 character-time days_since_last_progress，≥ 14 天 → 自动 paused。
3. **progress_log.ts 用事件 start_time**（角色时间）。

### 4.2 START 节点测试数据入口

**测试态 fixture**：
- timeline：`mengya_test_user_20260421.json` / `__doubleencoded.json`
- pursuits：`mengya__test_user.json`

**START 变量**：

| 变量名 | 测试态来源 | 线上态来源 |
|---|---|---|
| `start.char_id` | "mengya" | `sys.member_id` |
| `start.user_id` | "test_user" | `sys.user_id` |
| `start.schedule_timeline_raw` | fixture 整个（允许单/双层）| `sys.schedule_timeline`（§7 待新增）|
| `start.window_start` | fixture.ended_at - 24h | `sys.current_time - 24h` |
| **`start.pursuits_library`** | **fixture 整个 payload JSON 字符串** | **`sys.pursuits_library`**（中控 source=0 从 `pursuits_library` 表查注入）|

> schedule_timeline 的容错 schema（`{"events":[...]}` / 直接数组 / 双层编码）见 `pursuits_input_contract_v1.md` §4。
>
> **`start.pursuits_library`（2026-04-21 晚 2 补）**：MB 读库同 MA，走 sys.* 注入，不再有 tool(SQL) 节点；MB-01 改为 code 节点做 JSON parse + count。

### 4.3 节点链

```
[MB-00 START]
    ↓
[MB-01 解析 pursuits_library 注入] (code)    ← v3.2 由 tool 改为 code
    ↓
[MB-02 解析 timeline（双/单层透明）] (code)
    ↓
[MB-03 timeline 预处理 + 角色时间计算] (code)  ← v3 扩职责
    ↓
[MB-04 LLM 判定变更（仅 progress / completed / priority）] (tool → doubao-1.5 pro 32k)
    ↓
[MB-05 解析 + 硬校验] (code)
    ↓
[MB-06 应用变更 + auto_paused 扫描 + 重建 top-5 + 组装 new_library] (code)  ← v3 扩职责 + v3.2 补 payload 组装
    ↓
[MB-08 写 pursuits_top5_cache]    [MB-09 写 uar_daily_counter 缓存]   ← v3.2 原 MB-07 写库 tool 删除
    ↓                                        ↓
    └─────────── [MB-END] ──────────────────┘  ← output { new_library, auto_paused_summary }
```

> MB-08 和 MB-09 并行（都是 variable-assigner，无依赖）。

### 4.4 节点详表

```
╭─── [MB-00 START] / [MB-01 解析 pursuits_library 注入] ───
│ MB-00: type=start，入参见 §4.2。
│ MB-01: type=code（v3.2 由 tool 改为 code），与 MA-01 同结构。
│   入参: lib_raw ← ${start.pursuits_library}
│   出参: library:string（透传）/ active_count:number / paused_count:number
│   逻辑: 同 MA-01（JSON.parse + filter(status) 计数）
│   为什么这么做: 中控 source=0 把 pursuits_library 表查好注入 sys.*，
│     工作流内不直接跑 SQL；参见 §0.2 DB 读规范。
╰──────────────────────────────────────────
```

```
╭─── [MB-02 解析 timeline] ─────────────────
│ id: Nmbxx02
│ type: code
│
│ 入参:
│   - raw ← ${start.schedule_timeline_raw}
│   - window_start ← ${start.window_start}
│
│ 出参:
│   - events: string（11 字段标准化后窗口内事件 JSON array 串）
│   - events_count: number
│   - full_events: string（窗口外也保留，用于 MB-03 的 gap 扫描）
│
│ 逻辑（对应 _parse_schedule_timeline_raw）:
│   1. 兼容 Dify END 双层编码：
│      try JSON.parse(raw) → 若仍是 string，再 JSON.parse 一次
│   2. 支持两种顶层：{events:[...]} 或 [...]（直接数组）
│   3. 过 start_dt ≥ window_start 的事件 → events（给 LLM 看）
│   4. 全量 → full_events（给 MB-03 算 gap）
│   5. 11 字段归一（补缺字段为空串）
│   6. return {...}
│
│ 为什么这么做：
│   双层编码来自 Dify END 节点的 bug（见 INV-007），必须透明兼容；
│   窗口过滤放这里是为了下游 LLM 只看近 24h，但角色时间算 gap 需要全量。
╰──────────────────────────────────────────
```

```
╭─── [MB-03 timeline 预处理 + 角色时间计算] ─
│ id: Nmbxx03
│ type: code
│
│ 入参:
│   - library ← ${Nmbxx01.library}
│   - events ← ${Nmbxx02.events}        # 窗口内事件
│   - full_timeline ← ${Nmbxx02.full_events}  # 不过滤的全量（用于 gap 扫描）
│   - now ← ${sys.current_time}
│
│ 出参:
│   - active_pursuits_digest: string
│   - paused_pursuits_digest: string
│   - events_digest_text: string
│   - character_time_ctx: string        # v3 新增，JSON 串
│     {
│       pursuit_id: {
│         character_days_since_created: number,
│         character_days_since_last_progress: number,
│         pacing_ratio: number                    # char_days / estimated_days
│       }
│     }
│
│ 逻辑（v3 新增角色时间计算）:
│   1. 对每个 lib.pursuits[i]:
│      a. 取 created_at；遍历 full_timeline 按 start_dt 升序
│      b. 累计 gap > 24h 的段总长 = pause_duration_real
│      c. character_days_since_created =
│           (now - created_at - pause_duration_real) / 86400_000
│      d. last_progress_ts = max(progress_log[*].ts) || created_at
│      e. 同样算 character_days_since_last_progress
│      f. estimated_days = span_to_days(estimated_span)
│           days_1_3 → 2 / week_1 → 7 / weeks_2_4 → 21
│           months_1_3 → 60 / months_3_12 → 180
│      g. pacing_ratio = character_days_since_created / estimated_days
│   2. events → "[step01] HH:MM @loc: desc" 文本块
│   3. active / paused digest 同 MA-03 格式
│
│ 为什么这么做：
│   - 角色时间算在 MB-03 而不是 MB-06，是因为 MB-06 还要给 LLM
│     输出做 auto_paused 交叉校验；提前算好让 MB-06 只做拼装。
│   - pacing_ratio 存起来供 §5 P2-改造-02 注入 pacing_tag 复用。
│     ——实际 MB-03 的输出不会跨工作流传；P2-改造-02 要重新算。
│     这里 MB 内部只用来做 auto_paused 的 14 天判定。
╰──────────────────────────────────────────
```

```
╭─── [MB-04 LLM 判定变更] ──────────────────
│ 与 MA-04 结构一致；prompt 模板 v3 差异：
│   - events_digest_text 替换 normalized_turns_text
│   - 只允许 3 桶：progress_updates / completed / priority_order
│   - **明确禁止** update_estimated_span / update_done_criterion /
│     new_pursuits / to_pause / to_revive（prompt 里显式列"禁区"）
│   - progress_updates 无 evidence_quote 要求（evidence = linked_event_id）
│     但必须指向 events 里存在的 event_id
│   - completed 需要 evidence_event_id + event 里必须含完成证据关键词
│     （prompt 约束，非 CODE 硬校验——完成判定相对明确）
│
│ Prompt 模板来源：pursuits_maintain_after_schedule.py::MB_PROMPT_V1
│
│ 为什么这么做：
│   - MB 视角只有 schedule_timeline，看不到对话；没法判断延期合理性
│     → 禁 update_estimated_span
│   - 同理 → 禁 update_done_criterion（对话里才可能修订条件）
│   - MB 不可能观测到"新想法出现"这种信号 → 禁 new_pursuits
╰──────────────────────────────────────────
```

```
╭─── [MB-05 解析 + 硬校验] ─────────────────
│ id: Nmbxx05
│ type: code
│
│ v3 校验规则：
│   1. 桶必须只包含 {progress_updates, completed, priority_order}
│      出现其他桶 → 整条 reject 该桶（不是整体失败，记 deprecated_ignored）
│   2. progress_updates[].pursuit_id 必须在 lib 里
│   3. progress_updates[].evidence_event_id 必须在 events 里
│   4. completed[].evidence_event_id 必须在 events 里
│   5. priority_order[] 覆盖全部 active pursuits
╰──────────────────────────────────────────
```

```
╭─── [MB-06 应用变更 + auto_paused + 重建 top-5] ─
│ id: Nmbxx06
│ type: code
│
│ 入参:
│   - library ← ${Nmbxx01.library}
│   - decision ← ${Nmbxx05.decision}
│   - events ← ${Nmbxx02.events}
│   - character_time_ctx ← ${Nmbxx03.character_time_ctx}
│   - char_id ← ${start.char_id}               # v3.2: 组装 payload 需要
│   - user_id ← ${start.user_id}
│
│ 出参:
│   - new_library: string                # v3.2: JSON.stringify({char_id, user_id, pursuits, updated_at})，交给 MB-END
│   - top5_cache: string
│   - auto_paused_summary: string       # 列出本次被自动暂停的 pid
│   - uar_daily_counter_init: string
│
│ 逻辑（v3）:
│   1. 应用 LLM 3 桶变更（progress_updates / completed / priority_order）
│      progress_log.push({
│         ts: events[eid].start_time,    # v3: 关联事件的时间
│         note: "...",
│         by: "MB",
│         evidence_ref: `event:${eid}`
│      })
│   2. linked_schedule_events.push(eid) 累加
│   3. **auto_paused 扫描**（v3 新增）:
│      对每个 status==active 的 pursuit:
│        ctx = character_time_ctx[pid]
│        if ctx.character_days_since_last_progress >= 14:
│           status = "paused"
│           progress_log.push({
│             ts: now,
│             note: "[auto_paused] 14 天角色时间无进展",
│             by: "MB",
│             evidence_ref: "system:auto_paused_rule"
│           })
│           auto_paused_list.push(pid)
│   4. top-5：只在 active 里按 (urgency, estimated_span) 排，或按 LLM
│      priority_order 取前 5
│   5. uar_daily_counter_init = {date: today_YYYYMMDD, count: 0}
│   6. return {...}
│
│ 为什么这么做：
│   - auto_paused 放在 MB 而不是 MA：MA 是每会话触发，1 天可能 0 次
│     或很多次，放 MA 会多次重复计算；MB 是每日首次 P2 cron 后固定
│     跑 1 次，最适合做"无进展清理"。
│   - 角色时间 ≥ 14 天而不是真实时间：防止离线挂机把角色"拖死"。
│   - 规则参数 14 天是从 estimated_span 的最短档位 days_1_3 的 ~5x
│     推出来的——给一个 pursuit 5 倍于承诺时长的宽限期再暂停，
│     大概率能挡住误杀又不会让僵尸 pursuit 堆积。
╰──────────────────────────────────────────
```

> **原 MB-07 写库 tool 节点已于 2026-04-21 晚 2 删除**——参见 §0.2 写规范 / §4.3 节点链说明。MB-06 组装 `new_library` payload 后直接流向 MB-END；MB-08 / MB-09 写缓存并行，不受影响。

```
╭─── [MB-08 写 pursuits_top5_cache] ────────
│ type: variable-assigner
│ 维度: user_id + member_id
│ key:  pursuits_top5_cache
│ ttl:  [23, 59, 59]
│ write_mode: over-write
│ 入参: ${Nmbxx06.top5_cache}
╰──────────────────────────────────────────
```

```
╭─── [MB-09 写 uar_daily_counter] ──────────
│ type: variable-assigner
│ 维度: user_id + member_id
│ key:  uar_daily_counter
│ ttl:  [23, 59, 59]
│ write_mode: over-write              # 每天 M-B 覆盖一次
│ 入参: ${Nmbxx06.uar_daily_counter_init}
│
│ 说明: 这是"0 服务端代码"的关键让步——每日的 UAR 配额不再由服务端
│       定时器，而是 M-B 每天首次跑时覆盖一次，P2 runtime 读缓存 + 递增。
╰──────────────────────────────────────────
```

```
╭─── [MB-END] ──────────────────────────────
│ type: end
│
│ output:
│   - new_library ← ${Nmbxx06.new_library}        # v3.2: 中控回调 upsert
│   - auto_paused_summary ← ${Nmbxx06.auto_paused_summary}
│
│ 中控职责（§7.6）:
│   UPDATE pursuits_library SET pursuits_json=new_library, updated_at=now()
│   WHERE char_id=? AND user_id=?
╰──────────────────────────────────────────
```

### 4.5 数据链测试（P3）

| 单测 | 输入 fixture | 校验点 |
|---|---|---|
| ut-mb-01 | single-encoded timeline | MB-02.events_count==4，MB-06 产 2 progress |
| ut-mb-02 | double-encoded timeline | 与 ut-mb-01 完全一致 |
| ut-mb-03 | 空 events | MB-06 变更全 0，top-5 按 lib.active 顺序 |
| **ut-mb-04 (T2)** | timeline 含 3 天 gap（离线段）+ pursuit 15 天前创建但 gap 占 5 天 | character_days_since_created ≈ 10；不触发 auto_paused |
| **ut-mb-05 (T3)** | pursuit 15 天前创建无 gap，无 progress_log | MB-06.auto_paused_summary 含该 pid；status=paused |
| **ut-mb-06 (T4)** | LLM 违规输出 update_estimated_span 桶 | MB-05 丢弃该桶；其他桶保留 |

---

## §5 工作流 #4：P2 future_plan_to_schedule 改造

### 5.1 改造目标

> ⚠️ **本节是 P2 一次性落地改造的单一权威清单**，包含 **4 层 + validator 对齐** 的全部改动。
> 其中 LAYER1 / LAYER2 / validator R11·R14·R17 来自 **2026-04-20 `sim_phase1_results.md` 的沙盒优化**（mode-60% **95% → 16%** / 5-seed agg；扰动因果链触发率 32.8% ≈ 设计目标 30%），尚未迁回线上；pursuits 本轮必须把它们一并打包，否则这波优化会在合入时丢失。

在原有 P2 工作流（30 节点，不动拓扑）里做 **4 层改动**：

| 层 | 性质 | 来源 | 效果 |
|---|---|---|---|
| **LAYER1** | N17759173714860 CODE 节点扩字段 + N1775917544153 prompt 追加段 | sim_phase1 | mode-60 从 **94.5% → 16.3%**（5-seed agg）|
| **LAYER2** | 同上 CODE 节点再加 disturbance.roll + prompt 追加段 | sim_phase1 | 扰动触发率 **32.8%**（5-seed agg）|
| **LAYER3** | 新增 extractor + code 节点读 pursuits_top5_cache 注入 | pursuits 本轮 | 日程被 pursuit 牵引（v3 强化：pacing_tag + recent_scheduled）|
| **LAYER4** | 同上 code 节点读 uar_daily_counter 注入 + 新增回写节点 | pursuits 本轮 | UAR 判定 + 每日配额 |

v3 **强化 P2-改造-02**，让它同时承担：
- 读 pursuits_top5_cache
- **算角色时间 + pacing_tag**（v3 新增）
- **注入最近 7 天已排事件的 recent_scheduled**（v3 新增）
- 算 UAR remaining

### 5.2 改动节点清单

| 节点 | 动作 | 说明 |
|---|---|---|
| **N17759173714860（原 CODE 节点）** | **扩字段 events_budget / disturbance（LAYER1+2）** | 沿用 sim_phase1 已验证的计算式（见 `sandbox/services/offline_constraint.py`）|
| **[P2-改造-01] 读 pursuits+uar 缓存** | **新增 variable-extractor** | 在 N1775917544153 **前** 插入；v3 新增读 schedule_timeline |
| **[P2-改造-02] 组装 pursuits_block + pacing + recent_scheduled + uar_rules_block** | **新增 code**（v3 扩）| 在 extractor 后、LLM 节点前 |
| **N1775917544153（原 LLM 节点）** | **改 prompt 模板**：追加 LAYER1 + LAYER2 + EXPRESSION_ENUM_REMINDER + LAYER3 + LAYER4 五段 | 模板只改尾段，主体不动；prompt 变量相应新增 |
| **[P2-改造-03a] UAR 计数判定** | **新增 code（LAYER4）** | 扫 LLM 输出是否含 `【求助】`，产出 new_counter |
| **[P2-改造-03b] UAR 计数回写** | **新增 variable-assigner（LAYER4）** | 写 uar_daily_counter 缓存 |

### 5.3 节点详表

```
╭─── N17759173714860（原 CODE，扩字段）────
│ type: code（不变）
│ code_language: javascript（不变）
│
│ 入参 variables（在原有基础上保留，不删）:
│   - ... 原有全部入参 ...
│   - current_time ← ${sys.current_time}     # 已有
│
│ 出参（在原有基础上新增 2 字段）:
│   - ... 原有全部出参 ...
│   - events_budget: object                   # 新增（LAYER1）
│       {
│         remaining: number,                  # 今日剩余事件额度
│         suggested_range: [min, max],        # 推荐时长区间（展宽后的分钟数）
│         must_be_sleep: boolean,             # 本步是否必须写睡眠事件
│         min_per_event: number               # 40（与 validator R11 floor 对齐）
│       }
│   - disturbance: object                     # 新增（LAYER2）
│       {
│         roll: "none" | "injury" | "social" | "bio" | "impulse" | "env",
│         duration_target_minutes: [min, max],  # 推荐 [40, 55]（避开 60 反弹）
│         must_switch_location: boolean
│       }
│   - events_budget_text: string              # 渲染给 prompt 的文本段
│   - disturbance_text: string
│
│ 逻辑（新增，沿用沙盒已验证的计算式）:
│   1. 按 today_log 算剩余额度 remaining
│   2. suggested_range = [base_min * 0.65, base_max * 1.45]（展宽）
│   3. frontier 距 01:30 <= 1h → must_be_sleep=true
│   4. Math.random() < 0.30 → disturbance.roll 随机抽 5 类之一；否则 "none"
│   5. return { ...原有字段, events_budget, disturbance, events_budget_text, disturbance_text }
│
│ 沙盒对应: sandbox/services/offline_constraint.py
│
│ ⚠️ 重要: 本节点的风险在于"改动原 CODE 会不会破坏既有流"——
│       必须在 P3 单测里对"原字段"做对拍（输入同样的 sys.*，原字段输出字节一致）。
╰──────────────────────────────────────────
```

```
╭─── [P2-改造-01 读 pursuits+uar 缓存] ─────
│ type: variable-extractor
│
│ 读 1: 维度 user_id+member_id, key: pursuits_top5_cache → pursuits_top5_raw
│ 读 2: 维度 user_id+member_id, key: uar_daily_counter → uar_counter_raw
│
│ v3 新增读 3:
│   维度 user_id+member_id, key: schedule_timeline（若作 cache 存在）
│   或改从 sys.schedule_timeline 读
│   → schedule_timeline_raw
│
│ 若 schedule_timeline 无法走 extractor（线上现实是 DB 读），
│ 改用 tool 节点 schedule_timeline_read 并把 [P2-改造-01] 拆成两节点。
│ 沙盒阶段先假设能走 sys 全局或 cache。
│
│ 出参:
│   - pursuits_top5_raw: string（JSON 串或空串）
│   - uar_counter_raw:  string
│   - schedule_timeline_raw: string
│
│ 为什么这么做：
│   - P2-改造-02 需要 schedule_timeline 才能算 character time 和
│     recent_scheduled 去重；不能让它自己再读一次（CODE 不能读 DB/缓存）。
│   - 风险: cheatsheet §3.2 维度不一致返回空——M-A/M-B 必须用同样的
│     user_id+member_id 两维度写，否则 P2 这里读空。
╰──────────────────────────────────────────
```

```
╭─── [P2-改造-02 组装 pursuits_block + uar_rules_block] ──
│ type: code
│
│ 入参 variables:
│   - pursuits_top5_raw ← ${N(P2-改造-01).pursuits_top5_raw}
│   - uar_counter_raw ← ${N(P2-改造-01).uar_counter_raw}
│   - schedule_timeline_raw ← ${N(P2-改造-01).schedule_timeline_raw}
│   - today ← ${sys.current_time}
│
│ 出参（v3 扩）:
│   - pursuits_block: string
│     （每条渲染为:
│       "{N}) 【{urgency_cn}】{title} [{pacing_tag}]
│        当下: {current_stage}
│        完成条件: {done_criterion}
│        近7日已排: {recent_scheduled_line}"）
│   - uar_rules_block: string
│   - uar_remaining: number
│
│ 逻辑（v3 重写）:
│   1. 解 pursuits_top5_raw
│   2. 解 schedule_timeline_raw（双层编码透明）
│   3. 对每条 top5 pursuit:
│      a. 算 character_time（复刻 MB-03 的 gap 扫描算法）:
│         pause_duration = sum(gap > 24h)
│         char_days_since_created = (now - created_at - pause_duration) / 86400k
│         estimated_days = span_to_days(estimated_span)
│         pacing_ratio = char_days_since_created / estimated_days
│      b. pacing_tag 分桶:
│         ratio < 0.4   → "早期铺垫"
│         ratio < 0.75  → "推进期"
│         ratio < 1.0   → "收尾期"
│         ratio < 1.3   → "延迟期"
│         ratio >= 1.3  → "严重逾期"
│      c. recent_scheduled: 扫 timeline 近 7 天（real time 窗口即可），
│         过 event.linked_pursuit_id == this.id 的事件，
│         取 summary 拼成 "【近7日已排】{date1} {summary1}; {date2} {summary2}; ..."
│         最多 5 条；无则 "【近7日已排】无"
│   4. 渲染 pursuits_block 多行文本
│   5. 算 uar_remaining:
│      若 uar_counter_raw 空或 date!=today → remaining=1
│      否则 remaining = max(0, 1 - count)
│   6. 拼 uar_rules_block（替换 {{remaining_today}}）
│   7. return {...}
│
│ 为什么这么做（**v3 核心新增**）：
│   - **pacing_tag** 是给 LLM 的"进度压力"提示。不带标签时，LLM 会
│     反复在同一 pursuit 上加小步推进事件（偷懒）；带上"严重逾期"
│     后，LLM 会倾向生成收尾性事件或直接绕开。这是**软护栏**——
│     不强制生成什么，只给 LLM 背景知识。
│   - **recent_scheduled** 是给 LLM 的"去重参考"。过去 7 天已排过
│     "买咖啡 / 整理简历 / 查资料..." 时，LLM 再看到还会倾向生成
│     "再整理一次简历"；把这些事实摆在面前，LLM 多数情况会换花样。
│   - 两个都放在 P2 prompt 而不是 M-A/M-B：
│     - M-A/M-B 不生成事件；做护栏注入白费流量。
│     - 护栏要作用在"生成事件的那一刻"，P2 是唯一生成入口。
│   - 不用硬禁（CODE 层 post-filter）的原因：
│     - 硬禁会把"合理的延续性事件"也误杀（比如第 2 天接着做同件事）。
│     - LLM 自觉回避的失败率 < 误杀率，整体体验更好。
│
│ 沙盒对应: sandbox/tools/p2_patch02_renderer.py
╰──────────────────────────────────────────
```

```
╭─── N1775917544153（原 LLM 节点，改 prompt）
│ type: tool（不变）
│ tool_key: doubao-1.5 pro 32k（不变）
│
│ variables[] 结构（不变，仍是 2 条）:
│   - prompt (string, value=<改后整段 prompt 文本，含新增 5 段>)
│   - user_input (string, value="Output fixed 7 lines only.")
│
│ prompt 文本改动（在主体后追加 5 段，Dify 原生 ${nodeId.field} 引用）:
│   ... [原有 prompt 主体，含既有 31 个 ${...} 占位符] ...
│
│   === LAYER1 反 mode-60 指令 ===
│   本次生成请遵守下列事件预算与时长建议（已按今日已用额度动态算出）：
│   ${N17759173714860.events_budget_text}
│
│   === LAYER2 扰动抽签 ===
│   ${N17759173714860.disturbance_text}
│
│   === 表情 reminder（R06 专用）===
│   表情字段只能选：发呆 / 打盹 / 思考 / 工作 / 平静（误写 R06 fail，
│   常见错误："专注"=思考, "紧张"/"兴奋"/"生气" 一律选 平静）。
│
│   === LAYER3 pursuits 优先推进 ===
│   ${N(P2-改造-02).pursuits_block}
│   （v3 注入的 block 里自带 【pacing_tag】 和 【近7日已排】 两行；
│    prompt 用一句话约束："请避免与【近7日已排】中事件同质；严重逾期的
│    pursuit 优先安排收尾性事件"）
│
│   === LAYER4 UAR 求助额度 ===
│   ${N(P2-改造-02).uar_rules_block}
│
│ ⚠️ Dify prompt 占位符规则（线上 parity）:
│   prompt 文本里的 ${nodeId.field} 是 Dify **全局引用**，运行时自动
│   从 workflow 上下文解析；**不需要在 variables[] 里再映射一份**。
│   线上 N1775917544153 现有 31 个 ${...} 引用，variables[] 仅 2 条。
│
│ 输出格式扩展（由 prompt 指令约束，不是节点字段）:
│   原 7 行格式后追加:
│     【关联】{pursuit_id}              # LAYER3 效果
│     【求助】{uar_json}                # LAYER4 效果，可选
╰──────────────────────────────────────────
```

```
╭─── [P2-改造-03a UAR 计数判定] ────────────
│ type: code
│   入参: event_raw ← ${N1775917544153.output}
│         uar_remaining ← ${N(P2-改造-02).uar_remaining}
│         uar_counter_raw ← ${N(P2-改造-01).uar_counter_raw}
│         today ← ${sys.current_time}
│   逻辑:
│     1. 解析 event_raw 看是否含 "【求助】" 行
│     2. 若含且 uar_remaining>0:
│        new_counter = {date: today, count: (prev_count||0)+1}
│     3. 否则 new_counter = uar_counter_raw（透传）
│     4. return { new_counter: JSON.stringify(new_counter) }
╰──────────────────────────────────────────
```

```
╭─── [P2-改造-03b UAR 计数回写] ────────────
│ type: variable-assigner
│   维度: user_id + member_id
│   key:  uar_daily_counter
│   ttl:  [23, 59, 59]
│   write_mode: over-write
│   入参: ${N(P2-改造-03a).new_counter}
╰──────────────────────────────────────────
```

### 5.4 event_validator 扩展（服务端事件落盘时的校验）

这部分**不在工作流节点内**，在服务端 schedule event 落盘环节。**一次性对齐 2 批规则**：

#### 5.4.1 LAYER1+2 对齐（sim_phase1 产出，首次上线）

| 规则 | 原值 | 新值 | 动作 |
|---|---|---|---|
| **R11** 非睡眠事件最小时长 | ≥ 35 min | **≥ 40 min** | hard_fail |
| **R14** 同 scene_combo 二次使用 | 禁止 | **sleep 事件豁免**（夜睡同卧室合法）| hard_fail（仅非 sleep）|
| **R17** 短事件累计 ≥2 则 ≥60 min | 原规则 | **若 events_budget.suggested_range 存在则被 override**；否则保留 | hard_fail（仅 fallback）|

这三条配合 N17759173714860 的新增 `events_budget` 字段；不改这三条的话 layer1/2 就跑不起来。

#### 5.4.2 LAYER3+4 新规则（UAR + pursuit 关联，本轮新增）

| 规则 | 校验 | 动作 |
|---|---|---|
| R26 | `【关联】` 行必须指向 active pursuit | 不合规 → soft_fail |
| R27-R29 | `【求助】` JSON 字段完整性 | hard_fail |
| R30 | window_minutes ∈ [15, 180] | hard_fail |
| R31 | start_dt.time ∈ [10:00, 21:59] | hard_fail |
| R32 | if_absent_plan.branches ≥ 2 | hard_fail |
| R33 | 黑名单词汇（"转账"/"身份证"等）| hard_fail |

沙盒对应：`sandbox/services/event_validator.py` 的 R11/R14/R17/R26-R33 共 10 条已就位。

### 5.5 数据链测试（P3）

**LAYER1/2 相关**（补回归，防 v2 改动破坏 sim_phase1 已验证的效果）：

| 单测 | 输入 | 校验点 |
|---|---|---|
| ut-p2-layer1-01 | 5-seed 全天仿真（layer1）| 聚合 mode-60% ≤ 25%（5-seed agg 目标；sim_phase1 §5 基线 16.3%）|
| ut-p2-layer1-02 | 同上 | hard_fail_rate ≤ 5% |
| ut-p2-layer2-01 | 5-seed 全天仿真（layer1_2）| 扰动触发率 ∈ [25%, 40%]（设计 30%；sim_phase1 §5 基线 32.8%）|
| ut-p2-codenode-01 | 原字段对拍 | N17759173714860 的原有字段逐字节一致（不回归破坏）|

**LAYER3/4 相关**（本轮新增）：

| 单测 | 输入 fixture | 校验点 |
|---|---|---|
| ut-p2-03 | pursuits_top5_cache 已写 + uar_counter 空 | P2-改造-02: block 非空, uar_remaining=1 |
| ut-p2-04 | pursuits_top5_cache 空 | P2-改造-02: block="", uar_remaining=1（降级）|
| ut-p2-05 | uar_counter={date:今天,count:1} | uar_remaining=0，LAYER4 禁用生成 |
| **ut-p2-06 (T6a)** | pursuit created 30 天前 + timeline 连续 + estimated_span=week_1 | pacing_tag == "严重逾期" |
| **ut-p2-06b (T6b)** | 同上但 timeline 含 7 天 gap | character_days ≈ 23 → 仍 "严重逾期" |
| **ut-p2-07 (T6c)** | 近 7 天已排 "买咖啡" 3 次 linked to pid=pur_001 | recent_scheduled_line 含 3 条，LLM 新生成不再出现"买咖啡"（抽查 5 seed）|

---

## §6 工作流 #5：baji_chat_all 改造（UAR 回调注入）

### 6.1 改造目标

对话时，如果今天有未兑付的 UAR（用户没上线 → 30min 后 fallback 触发 → 写了 `if_absent_plan` 结果到 `schedule_timeline`），下次对话开场要让 AI 主动提这件事。

**v3 方案**（零服务端业务代码）：baji_chat_all 插 **callback_injector**——对话每 turn 跑一次，从 `schedule_timeline`【DB】扫描近 12h 内含 `[SOLO]` / `[FAILED]` / `[DEFERRED]` 前缀的事件，取最近 1 条，拼成一行注入到对话 prompt。纯读 + 拼串，无状态。

BCA 不读 pursuits，不需要随 v3 schema 改动。

### 6.2 改动节点清单

| 节点 | 动作 | 说明 |
|---|---|---|
| **[BCA-改造-01] 读 schedule_timeline** | **新增 variable-extractor 或 tool** | 若 `sys.schedule_timeline` 已存在（§7 需新增），用 extractor；否则 tool 调 DB |
| **[BCA-改造-02] 扫描 fallback 事件** | **新增 code** | 产出 `callback_injection_line`（空串或一行自然语言）|
| 对话主 LLM 节点（原有）| **改 prompt 模板** | 加占位符 `{{callback_injection_line}}` |

### 6.3 节点详表

```
╭─── [BCA-改造-01 读 schedule_timeline] ────
│ 方案 A（推荐，若线上 sys.schedule_timeline 可加入 sys.* 清单 §7）:
│   type: variable-extractor 或直接 ${sys.schedule_timeline}
│
│ 方案 B（兜底，若中控拒绝加 sys.*）:
│   type: tool, tool_key: schedule_timeline_read
│   入参: char_id, user_id
│
│ 出参:
│   - timeline_raw: string（双层编码透明兼容）
╰──────────────────────────────────────────
```

```
╭─── [BCA-改造-02 扫描 fallback 事件] ──────
│ type: code
│
│ 入参:
│   - timeline_raw ← ${BCA-改造-01 输出}
│   - now ← ${sys.current_time}
│   - baji_records_50 ← ${sys.baji_records_50}  # 用于"已提过则不重复"
│
│ 出参:
│   - callback_injection_line: string（空串或一行，如"（昨晚我试着自己去问了同事，结论是...）"）
│
│ 逻辑:
│   1. 解析 timeline（兼容双层编码）
│   2. 过 end_dt 在 [now-12h, now]、description 前缀 ∈ {[SOLO], [FAILED], [DEFERRED]}
│   3. 按 end_dt 倒序取第 1 条
│   4. 扫 baji_records_50 最近 20 条 assistant 内容，若已包含事件 summary 关键词 → 返回 ""
│   5. 否则按模板拼一行自然语言注入
│
│ 特性: 纯函数，零状态，每 turn 都算（<5ms，可接受）
╰──────────────────────────────────────────
```

```
╭─── 对话主 LLM 节点（原有，改 prompt）────
│ prompt 末段新增占位符:
│   {{callback_injection_line}}
│
│ 入参 variables 新增:
│   - callback_injection_line ← ${N(BCA-改造-02).callback_injection_line}
╰──────────────────────────────────────────
```

### 6.4 数据链测试（P3）

| 单测 | 输入 fixture | 校验点 |
|---|---|---|
| ut-bca-01 | timeline 含一条 [SOLO] 事件（2h 前）+ baji 未提过 | 产出非空 line |
| ut-bca-02 | timeline 含一条 [SOLO] 事件 + baji 已提过关键词 | 产出 "" |
| ut-bca-03 | timeline 空 | 产出 "" |

---

## §7 中控配置改动清单（诚实披露）

> 这些是"**配置变更**"不是"业务代码"，但仍然需要中控管理员手动在后台添加。发给中控的 PR 清单：

### 7.1 新增 sys.* 变量（source=0 / source=1 由中控定）

| sys 变量 | 用途 | 读取方 | 建议 source |
|---|---|---|---|
| `sys.pursuits_library` | pursuits 库整体 JSON（payload；**库不存在时注入 `""` 或 `null`**，CS-01 if-else 依赖此约定判空）| **CS-01** / MA-01 / MB-01 入参 | source=0（中控从 `pursuits_library` 表查）|
| `sys.schedule_timeline` | 当日时间线 JSON | M-B / baji_chat_all 入参 | source=0（中控从 `schedule_timeline` 表查）|
| `sys.baji_records_50` | 最近 50 轮原始对话（含伪消息）| **CS-02**（v3.2 新增读方）/ MA-02 入参 | source=0（现有）|

**v3.2 修订**：删除"替代方案：用 tool 节点走工具流程读 DB"。工作流节点**没有** SQL 能力，读 DB 的唯一正规路径就是 sys.* 注入（见 §0.2）。CS 从 `sys.baji_records_50` 读最近对话作为 `start.raw_records` 入参——如果中控当前还没把该变量注入 CS，中控侧必须配齐这一行注入声明。

### 7.2 新增工具流程（badge_llm_core 层，tool_key 列表）

| tool_key | 用途 | 工作流引用 |
|---|---|---|
| ~~`pursuits_lib_exists`~~ | ~~判库是否存在~~ | **v3.2 删除**——CS-01 改为 if-else on `${sys.pursuits_library}` 空判 |
| ~~`pursuits_lib_read`~~ | ~~读整个 library~~ | **v3.2 删除**——MA-01 / MB-01 改为 code 解析 `${sys.pursuits_library}` |
| ~~`pursuits_lib_write`~~ | ~~写 library~~ | **v3.2 晚 2 再删除**——CS-END-ok / MA-END / MB-END 输出 `new_library`，中控回调 upsert；与 P2 schedule_timeline / P3 future_plan 服务端写入流程一致 |
| `schedule_timeline_read`（如方案 B）| 读时间线 | BCA-改造-01 方案 B |

**v3.2 最终收窄（晚 2）**：原计划 4 个 `pursuits_lib_*` 工具流程**全部删除**。pursuits 工作流对 DB 的所有交互都由"**中控 source=0 预填 sys.* 注入（读）**"+"**工作流 END 透传 payload 中控 upsert（写）**"两条正规路径完成；只留可选的 `schedule_timeline_read`（BCA 改造方案 B，与 pursuits 无关）。这条路径与现有 P2 `future_plan_to_schedule` / P3 里程碑工作流的服务端对接方式**完全一致**，不引入任何新模式。

### 7.3 新增缓存 key

| 维度 | key | ttl | 写方 | 读方 | 备注 |
|---|---|---|---|---|---|
| user_id+member_id | `pursuits_top5_cache` | `[23,59,59]` | MA-08 / MB-08 | P2-改造-01 | pursuits v3.2 |
| user_id+member_id | `uar_daily_count` | `[23,59,59]` | MB-09 / P2-改造-03b（UAR 生成后 +1） | P2-改造-01 / MB-UAR-01 | **v0.1（2026-04-21）命名统一**：原 `uar_daily_counter` 与 `user_assist_request_design_v0.md §A.2` 不一致，统一为 `uar_daily_count`；所有出现处同步 |
| user_id+member_id | `uar_weekly_count` | `[167,59,59]` | MB-UAR-02（UAR 生成后 +1） | MB-UAR-01 | **UAR v0.1 新增**；7d 上限 3 条；非严格滑动窗（见 UAR v0 §A.4 已决点 #3）|
| user_id+member_id | `active_uar` | `[0,30,0]` | MB-UAR-02（生成） | baji_chat_all 起点；MA-UAR-01（结算清空）；MB-UAR-FALLBACK-00（读判空）| **UAR v0.1 新增**；30min TTL 对齐 `assist_window`；联调前抓一条 trace 验证 TTL 语义 |
| user_id+member_id | `post_assist_callback_queue` | `[23,59,59]` | MB-UAR-FALLBACK-00（fallback append）；baji_chat_all 消费后（剔除 head）| baji_chat_all 起点 | **UAR v0.1 新增**；FIFO；与 P3 `hook_injection_queue` 独立 |
| user_id+member_id | `last_uar_ref` | `[24,0,0]` | MB-UAR-02（生成时同步写）；MB-UAR-FALLBACK-00（处理完清空）| MB-UAR-FALLBACK-00 | **UAR v0.1 新增（方案 B）**；承载 UAR pending 态，**不**写 DB；详见 `user_assist_request_design_v0.md §A.3 + §B.4.1` |

**UAR 缓存补充说明（2026-04-21）**：
- UAR 相关 5 个 key（后 5 行）的权威定义在 `user_assist_request_design_v0.md §A.2`，本表只做中控配置项收录。
- 维度默认 `sharedVariable:{member_id}:{user_id}`（沿用线上约定；`assigned_variables = [sys.user_id, sys.member_id]`）。
- 命名统一：**`uar_daily_count`**（不是 `uar_daily_counter`）；下文 §5 prompt 注入节点 / §6.2 P2 改造节点描述中所有 `uar_daily_counter` 出现处均应同步改名（后续 v3.3 编辑时清理）。

### 7.4 新增 DB 表

#### 7.4.1 `pursuits_library` 表 DDL（主表）

**设计决定**：单行一用户（`char_id` × `user_id`），pursuits 全量以 JSON blob 存 `pursuits_json` 列；不做规范化拆表（工作流端总是整份读整份写，无需关系查询）。

```sql
CREATE TABLE pursuits_library (
  char_id                 BIGINT       NOT NULL,
  user_id                 BIGINT       NOT NULL,

  -- 核心 blob：14 字段 pursuit 对象数组（结构见 §0.6 + §7.4.2）
  pursuits_json           JSON         NOT NULL,

  -- UAR 审计列（v3.2 预留；UAR 详细设计上线前可为空）
  -- 结构：array of UAR records（见 §7.4.3）
  assist_request_history  JSON         NULL DEFAULT NULL,

  -- 时间戳
  created_at              DATETIME(3)  NOT NULL,
  updated_at              DATETIME(3)  NOT NULL,

  PRIMARY KEY (char_id, user_id),
  INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='角色自驱目标库 v3.2：一行 = 一个(角色, 用户)对，pursuits_json 是 14 字段对象数组';
```

**字段说明**：

| 列 | 类型 | 谁写 | 谁读 | 备注 |
|---|---|---|---|---|
| `char_id` | BIGINT | CS 建库时固化 | 全部 | = `sys.member_id`，联合主键 |
| `user_id` | BIGINT | CS 建库时固化 | 全部 | 联合主键 |
| `pursuits_json` | JSON | CS-END-ok / MA-END / MB-END 回调里由中控 upsert | MA / MB / P2 node21 | **整体覆盖写**，不做字段级 patch |
| `assist_request_history` | JSON NULL | UAR 工作流上线后由 UAR 生成/消费节点 upsert（与 `pursuits_json` **独立**，不同写入路径） | UAR 回放 / 审计查询 | v3.2 阶段先建列、置 NULL；等 UAR 详设完成后再写 |
| `created_at` | DATETIME(3) | CS 建库时 | — | 毫秒精度 |
| `updated_at` | DATETIME(3) | 每次 upsert | 索引用于回放 / 审计范围查询 | 毫秒精度 |

**索引说明**：
- **主键** `(char_id, user_id)` —— 覆盖所有 CS/MA/MB upsert 查询（点查）；
- **二级索引** `idx_updated_at` —— 给离线审计、running window 查询用；不是热路径，选 B-tree 即可。

**upsert 语义**（中控侧统一写法）：
```sql
-- PostgreSQL
INSERT INTO pursuits_library (char_id, user_id, pursuits_json, created_at, updated_at)
VALUES (?, ?, ?::jsonb, NOW(), NOW())
ON CONFLICT (char_id, user_id) DO UPDATE
  SET pursuits_json = EXCLUDED.pursuits_json,
      updated_at    = EXCLUDED.updated_at;
-- assist_request_history 不在这个写路径里动（走 UAR 工作流独立 upsert）

-- MySQL 8+ 等价写法
INSERT INTO pursuits_library (char_id, user_id, pursuits_json, created_at, updated_at)
VALUES (?, ?, CAST(? AS JSON), NOW(3), NOW(3))
AS new
ON DUPLICATE KEY UPDATE
  pursuits_json = new.pursuits_json,
  updated_at    = new.updated_at;
```

---

#### 7.4.2 `pursuits_json` 内每个 pursuit 对象的 14 字段（与 §0.6 同步）

```jsonc
{
  // 业务字段（7）—— LLM 可见、可写
  "title":           "string, ≤20 字",
  "dimension":       "家人|社交|工作|兴趣|约定|感情|误会|健康|生活|其他",
  "current_stage":   "string, ≤40 字",
  "urgency":         "hard|medium|soft",
  "estimated_span":  "X天 / X周 / X月 / 持续性",
  "done_criterion":  "string, ≤30 字",
  "origin_hint":     "string, ≤30 字",

  // 元数据（5）—— 系统管理，LLM 不改
  "id":              "pur_NNN, e.g. pur_001",
  "status":          "active|paused|completed|dropped",
  "created_at":      "ISO8601",
  "updated_at":      "ISO8601",
  "source":          "cold_start|maintain_after_chat|maintain_after_schedule",

  // 追踪数组（2）
  "progress_log":           [ { "by": "MA|MB", "summary": "string", "event_refs": ["evt_id", ...], "ts": "ISO8601" } ],
  "linked_schedule_events": [ "evt_id", ... ]
}
```

**注**：`evidence_message_ref`（MA 硬校验用的对话 turn 号引用）是 MA LLM 输出字段，**不落库**；校验通过后其语义并入 `progress_log[-1].event_refs`。

---

#### 7.4.3 `assist_request_history` 内每条 UAR record 的 schema（v3.2 预留；UAR 详设时扩充）

> **本节状态**：UAR 功能详细设计还在进行。以下 schema 是 `user_assist_request_design_v0.md` + §9 完整示例推导出的**最小可落库形态**，DB 建列时按这个结构预留即可；UAR 详设完成后若要加字段，走 `JSON` 列的 schema-less 扩展，**不需要再改表结构**。

```jsonc
[
  {
    // 身份
    "uar_id":             "uar_YYYYMMDD_NNN",              // 唯一；DB 不做外键，只是字符串
    "linked_pursuit_id":  "pur_NNN",                       // 指向同表 pursuits_json[i].id
    "linked_event_id":    "evt_YYYYMMDD_HHMMSS_NNN",       // 指向 schedule_timeline 里的事件

    // 时间
    "created_at":         "ISO8601",                       // UAR 生成时（M-B 节点内）
    "deadline_at":        "ISO8601",                       // 生成时 +30min（window_minutes）
    "resolved_at":        "ISO8601 | null",                // 用户响应或 fallback 落定时

    // 结果分类（`resolution_type` / `resolved_at` / `quality_impact` 在生成时为占位；UAR 结算时回填）
    "resolution_type":    "pending | user_responded | self_resolve_with_cost | partial_fail | defer",
    "quality_impact":     "pending | clean | partial | damaged",
    //  ↑ 对应 resolution_type：user_responded→clean；self_resolve_with_cost→partial；partial_fail→damaged；defer→保留上一次值

    // UAR 请求内容（LLM 在生成时产出；入库后不再变）
    "assist_request": {
      "what_user_can_do": "string, ≤60 字",                // "帮我拿个主意——红色还是黑色"
      "why_user":         "string, ≤40 字",                // "龙哥的口味我拿不准"
      "push_headline":    "string, ≤20 字"                 // 通知栏标题
    },

    // ⚠️ 预案：UAR 生成时 LLM **必须**一并产出（设计文档 §3.3「预存而不是动态重算」；§3.2 行 127 硬约束）
    //     不是"超时才写"——是"生成时就写好的 Plan B"。
    //     · user_responded 路径：预案存着但不执行（保留有审计价值：证明 Plan B 准备好了）
    //     · fallback 三路径（self_resolve_with_cost / partial_fail / defer）：预案被执行，progress_note 复制到 pursuits_json[i].progress_log
    "if_absent_plan": {
      "resolution_type":    "self_resolve_with_cost | partial_fail | defer",  // 预定的 fallback 分支（非最终 resolution_type）
      "narrative_self":     "string, ≤40 字",              // 角色自处理后的内心感受："最后挑了黑色那件，但一直觉得是不是太显眼"
      "narrative_callback": "string, ≤60 字",              // 下次对话开场独白："昨晚你没回我，我自己挑了黑色那件..."
      "quality_impact":     "clean | partial | damaged",   // 预计代价强度（LLM 按 60/30/10 分布产出，见 §3.2 行 207）
      "progress_note":      "[SOLO]|[FAILED]|[DEFERRED] + 一句话"  // fallback 命中时复制到 pursuits_json[i].progress_log
    },

    // 用户响应（仅 resolution_type=user_responded 时有值）
    "user_reply":       "string | null",                   // 用户那条消息原文
    "user_reply_turn":  "integer | null"                   // baji_records_50 里对应 turn 号
  }
]
```

**存储规则**（**v0.1 改定，2026-04-21**）：
- **单阶段写**（**不走两阶段**）：pending 态**不入库**——只留缓存 `last_uar_ref`（见 §7.3 + `user_assist_request_design_v0.md §A.3` "特别说明 `last_uar_ref`"段）。只有结算或 fallback 时才往 DB 写**一条终态** record。两个写入入口：
  - **入口 1（结算，MA-UAR-01 节点）**：LLM 判 `resolved=true/false`。`resolved=true` → 写 `resolution_type = "user_responded"`、`user_reply*` 有值、`if_absent_plan` 也一并写入（占审计位，留证据"Plan B 当时准备好了"）；`resolved=false` 则 MA 不写（留给 MB-UAR-FALLBACK-00 判）。
  - **入口 2（Fallback，MB-UAR-FALLBACK-00 节点）**：MB 检到 `last_uar_ref` 非空 + `active_uar` 空（TTL 过期）+ history 无对应 uar_id → 写 `resolution_type ∈ {self_resolve_with_cost, partial_fail, defer}`（来自 `if_absent_plan.resolution_type`）、`resolved_at = now` 等，整条终态 record 入库。
- **为什么不写 pending**：双写一致性 / DB 写放大 / history 语义稀释 / END payload 膨胀 4 个弊端；详见 `user_assist_request_design_v0.md §A.3`。
- **`if_absent_plan` 和 pursuits_json 的派生关系**：fallback 路径命中时，中控（或 UAR 工作流）把 `if_absent_plan.progress_note` **复制**一份到 `pursuits_json[i].progress_log`（i = `linked_pursuit_id` 对应的 pursuit），并追加 `uar_fallback: <resolution_type>` 字段，便于 M-A / M-B 后续判断（见设计文档 §9 完整示例行 340）。**完整 `if_absent_plan` 内容只落在 `assist_request_history`**，pursuits_json 只拿派生摘要。
- **裁剪策略**（**v0.1 改定**）：保留最近 **90 条**或 **180 天**（两者取早）；**由 MA-UAR-01 顺手裁剪**（每次结算写入后，丢弃溢出部分）；MB-UAR-FALLBACK-00 写入 fallback 记录时**不裁剪**（避免与 MA 并发写冲突）；**不设离线 cron**。
- **不参与热路径**：MA / MB / P2 node21 都**不读**这一列；只有 UAR 工作流自己的回放节点 + 后台审计查询会读。唯一例外：**MB-UAR-FALLBACK-00 会读**（判 uar_id 是否已结算），但读取发生在 MB-01 之前、不在 pursuits 读写主链路上。

---

#### 7.4.4 v3.2 不涉及、但 DB 工程师请**一并**建的辅助约束

1. **字符集** `utf8mb4`（中文 emoji 安全）；
2. **`pursuits_json`** 在 MySQL 8 下必须是 `JSON` 类型（不是 `TEXT`）——中控写入走 `JSON_VALID()` 校验前置；
3. **`assist_request_history`** 允许 NULL（现阶段），但建议默认值 `NULL` 而非 `'[]'`（节省空间 + 语义区分"从未生成 UAR"vs"历史清空"）；
4. **软删除不做**：pursuits 的 `status=dropped` 已承担软删除语义，DB 不加 `is_deleted` 列；
5. **无触发器 / 无存储过程**：所有业务逻辑在工作流 / 中控侧，DB 只做存储。

---

### 7.5 不需要的服务端改动（对比 v1）

| v1 说要的服务端 | v3 怎么做 | 说明 |
|---|---|---|
| post_assist_callback 队列 | BCA-改造-02 code 节点实时扫 timeline | 纯函数，无状态 |
| fallback 30min 轮询定时器 | **MB-UAR-FALLBACK-00 节点承担**（UAR v0.1，2026-04-21）| 下次 MB 运行时自检 `last_uar_ref` + history，接受 ≤2h 灰色窗口；**零新 cron**。详见 `user_assist_request_design_v0.md §A.4 已决点 #4 + §B.4.1` |
| UAR 日计数器定时归零 | MB-09 每天首次 M-B 覆盖 | 等价 |
| Push 通知 | ⚠️ **仍需服务端**：工作流没 Push 能力 | 见 §7.6 |

### 7.6 v3 仍然必须保留的服务端能力

| 能力 | 理由 | 工作量 |
|---|---|---|
| **`pursuits_library` 注入**（v3.2 晚 2 新增） | 工作流读 DB 的唯一路径 | 中控 source=0：CS / MA / MB 触发前查 `pursuits_library` 表注入 `sys.pursuits_library`（库不存在注入 `""` 或 `null`）|
| **`baji_records_50` 注入 给 CS**（v3.2 晚 2 新增） | CS 判闭环事件 + 抓最新对话 pursuit 需要 raw 对话 | MA 已有该 sys.* 注入；CS 同步补齐 |
| **`pursuits_library` 回写**（v3.2 晚 2 新增） | 工作流写 DB 的唯一路径 | 收到 CS-END-ok / MA-END / MB-END 的 `output.new_library`，`INSERT ... ON CONFLICT DO UPDATE` 到 `pursuits_library` 表；CS-END-skip 不写；与 schedule_timeline 回写一致 |
| **UAR 缓存 5 项的 sys.* 注入**（UAR v0.1，2026-04-21 新增） | UAR 工作流读缓存的唯一路径 | 中控 source=0：触发 MB 前注入 `sys.active_uar_raw / sys.uar_daily_count_raw / sys.uar_weekly_count_raw / sys.post_assist_callback_queue_raw / sys.last_uar_ref_raw`；触发 baji_chat_all 前注入前两项 + queue；详见 `user_assist_request_design_v0.md §A.1` |
| **`assist_request_history` DB 回写**（UAR v0.1 新增） | UAR 结算 / fallback 的审计入库 | 收到 MA-END 的 `uar_resolution` 字段（结算）或 MB-END 的 `uar_fallback_fired` 字段（fallback），`UPDATE pursuits_library SET assist_request_history = JSON_ARRAY_APPEND(...)` |
| **Push 通知** | 工作流不能直接触发推送 | UAR 生成时，服务端在事件落盘钩子里读 `push_headline` 字段发 Push |

**总结（v0.1 修订，2026-04-21）**：v1 说"0 服务端改动"不准确；v3.2 原为"注入 2 项 + 回写 1 项 + 1 个 cron + 1 个落盘钩子"；UAR v0.1 再精简为"**注入 2+5 项（read）+ 回写 1+1 项（write）+ 0 个 cron + 1 个落盘钩子**"——原 UAR fallback cron 撤销，改由 MB-UAR-FALLBACK-00 节点承担。注入/回写与 P2 `schedule_timeline` / P3 `future_plan` 现有中控编排模式完全同构，无新增集成模式成本。

**v3 无新增配置**（schema 改动全在 DB 表的 `pursuits_json` 内，schema-less）。

---

## §8 开发顺序（v3）

### Day 1（0.9 天）：schema + MA evidence_quote ✅ 完成

**产出**：
1. **删 `next_likely_actions`**：
   - `sandbox/tools/emit_pursuits_skeletons.py` 节点描述文本
   - `sandbox/tools/pursuits_cold_start.py::COLD_START_PROMPT_V1` 输出 schema
   - `sandbox/tools/pursuits_maintain_after_chat.py::MAINTAIN_PROMPT` 输入 digest / 输出 schema
   - `sandbox/tools/pursuits_maintain_after_schedule.py::MB_PROMPT_V1` 同上
   - 5 份 workflow JSON（`workflow/*-pursuits_v2.json`）的 prompt 字面量
   - 现有测试 fixture `sandbox/fixtures/pursuits/mengya__test_user.json` schema migration
2. **MA 新增 2 桶**：
   - MAINTAIN_PROMPT 新增 `update_estimated_span` / `update_done_criterion` 桶说明 + bad example + evidence 规则
   - `pursuits_maintain_after_chat.py::parse_response` 接受新桶
   - `apply_changes` 实现 2 桶应用
3. **MA-05 硬校验**：
   - `pursuits_maintain_after_chat.py` 新增 `_evidence_ok(turn_idx, quote, turns)` helper
   - evidence 校验失败放 `rejected` 数组，与其他桶解耦
4. **测试**：
   - T1 删字段回归（ut-cs-04）
   - T5 MA evidence 校验（ut-ma-04/05/06）

### Day 2（0.9 天）：角色时间 + 轻量护栏 + auto_paused ✅ 完成

**产出**：
1. **角色时间 helper**：
   - `sandbox/tools/character_time.py` 新模块，导出：
     - `paused_hours_in_window(timeline, from_ts, to_ts)` — scan gap > 24h
     - `character_days_since(created_at, now, timeline)`
     - `pacing_ratio(pursuit, now, timeline)`
     - `pacing_tag(ratio)`
     - `should_auto_pause(pursuit, now, timeline)`
   - 复刻到 Dify code 节点脚本（Day 3 P4 生成）
2. **MB auto_paused**：
   - `pursuits_maintain_after_schedule.py::apply_changes` 新增 auto_paused 扫描逻辑
   - MB_PROMPT_V1 明确写出"禁桶"列表
3. **P2-改造-02 护栏**：
   - `sandbox/tools/p2_patch02_renderer.py` 新模块，实现 pursuits_block 组装
   - 复刻到 Dify code 节点脚本
4. **progress_log.ts 语义**：
   - MA.apply_changes 使用 turn.ts
   - MB.apply_changes 使用 event.start_time
5. **测试**（19 条 T2/T3/T4/T6 全绿）：
   - T2 角色时间 gap 扣除（ut-mb-04）
   - T3 auto_paused 触发（ut-mb-05）
   - T4 MB 违规桶丢弃（ut-mb-06）
   - T6 pacing / recent_scheduled（ut-p2-06/06b/07）

### Day 2.5（2026-04-21 晚 hotfix-1）：closed-loop guard ✅ 完成

**产出**：
1. **输入契约沉淀文档**：`sandbox_notes/pursuits_input_contract_v1.md`（7 节，锁定 CS/MA/MB 三工作流的所有 start.* / sys.* 输入 schema）
2. **CS prompt 修订**：
   - `pursuits_coldstart_probe.py::COLD_START_PROMPT_V1` ❌ 表新增 2 行闭环样例
   - 自检从 3 条扩到 4 条（补 (d)）
3. **MA prompt 修订**：
   - `pursuits_maintain_after_chat.py::MAINTAIN_PROMPT` §5 new_pursuits 补"单轮闭环反例"块（含 3 反例 + 2 正例）
4. **Dify JSON 同步**：
   - 重跑 `python -m sandbox.tools.emit_pursuits_skeletons` 把新 prompt 灌到 5 份 workflow JSON
5. **回归测试**：
   - `sandbox/tests/test_pursuits_v3_prompt_guards.py` 9 条 T7 断言全绿

### Day 2.5b（2026-04-21 晚 hotfix-2）：DB 读走注入 + CS 补 raw_records 入参 ✅ 文档完成

**触发**：用户 2026-04-21 晚二次复审指出两点：
- v3 文档里 CS START 变量表没对话记录（raw_records），但 CS 需要它判"近期闭环事件" + 抓最新 pursuit。
- CS-01 / MA-01 / MB-01 都写成 `tool → DB read`，但 Dify 工作流节点没有 SQL 能力，这违反了"中控 source=0 预填 sys.*"的现有架构。

**产出（本次纯文档，待 Day 3 落 Dify）**：
1. **§0.2 DB 读/写规范重写**：
   - 读 DB：中控 source=0 预填 sys.*，工作流用 `if-else` / `code` 节点消费
   - 写 DB：工作流 END 节点透传 payload，中控回调 upsert（**v3.2 晚 2 补**，原计划保留 tool 写也删除）
2. **§2.2 CS START 补 2 行**：
   - `start.raw_records` ← `sys.baji_records_50`
   - `start.pursuits_library` ← `sys.pursuits_library`（库不存在时中控注入 `""` 或 `null`）
3. **§2.4 CS-01 由 tool(SQL) 改为 if-else on `${sys.pursuits_library}` 空判**；原 CS-01b 合并消失。
4. **§2.4 CS-02 入参加 `raw_records`，新增 `recent_chat_digest` 出参**（伪消息过滤后的对话文本段，供 CS-03 prompt 内嵌引用）。
5. **§2.4 CS-03 prompt 模板内嵌引用补 `${Nxxx02.recent_chat_digest}`**。
6. **§3.4 MA-01 / §4.4 MB-01 由 tool(SQL) 改为 code(parse sys.pursuits_library)**。
7. **写侧 3 节点全删**（v3.2 晚 2 补）：
   - §2.4 CS-05 删除，CS-04 扩出"组装 new_library"职责，CS-END-ok output 带 `new_library`
   - §3.4 MA-07 删除，MA-06 扩出 `char_id/user_id` 入参 + `new_library` 出参，MA-END output 带 `new_library`
   - §4.4 MB-07 删除，MB-06 同 MA-06 扩，MB-END output 带 `new_library`
8. **§7.1 sys.* 表补 sys.baji_records_50 的 CS-02 读方标注**；**§7.2 工具登记 `pursuits_lib_*` 全部删除**（3 个读写工具都不要）。
9. **§1 全局表 tool(DB) 列全部归 0**（CS/MA/MB 原各 2 tool 节点清空）。
10. **§7.6 中控职责表补 3 行**（注入 lib / 注入 records / 回写 lib），与 schedule_timeline 现有模式一致。
11. **§2.5 补 2 条 ut-cs 测试**（ut-cs-06 raw_records 伪消息过滤；ut-cs-07 sys 空判兜底）。

**待 Day 3 落地**：
- Dify CS JSON 骨架：CS-01 节点类型由 tool → if-else；CS-02 入参新增 raw_records；CS-03 prompt 模板追加"对话优先"段（COLD_START_PROMPT_V2）。
- Dify MA/MB JSON 骨架：MA-01 / MB-01 节点类型由 tool → code。
- emit_pursuits_skeletons 对应 regen。
- 中控侧：确保 `sys.pursuits_library` / `sys.baji_records_50` 已作为 CS 的 source=0 注入。

### Day 3+（P4/P5，延后）

- viz 嵌入新 trace
- Dify JSON 骨架更新（prompt 替换 + code 脚本嵌入 + Day 2.5b 的节点类型切换）
- 导入 Dify + prompt 调优（包含 COLD_START_PROMPT_V2 "对话优先"段）
- p2_patch02 Python 参考实现 port 到 emit_pursuits_skeletons JS 版（需要 schedule_timeline 注入）

---

## §9 v2 → v3 差异总结

| 项 | v2 | v3 |
|---|---|---|
| **Pursuit 业务字段** | 8（含 next_likely_actions）| **7（删 nla）** |
| MA 变更桶 | 6 | **8（+ update_estimated_span / update_done_criterion）** |
| MB 变更桶 | 5 | **3 + auto_paused（code 自动判定）** |
| MA evidence_quote | 无 | **所有状态性桶强制 + MA-05 硬校验** |
| `estimated_span` 改动权 | MA + MB | **仅 MA（带证据）** |
| `done_criterion` 改动权 | MA + MB | **仅 MA（带证据）** |
| 时间基准 | 真实时间 | **角色时间（schedule_timeline gap 扫描）** |
| auto_paused 判定 | 无 | **MB 扫 14 天角色时间无进展** |
| `progress_log[].ts` 语义 | 不明确 | **MA=turn 时间 / MB=event.start_time** |
| P2-改造-02 注入 | pursuits_block + uar_rules_block | **+ pacing_tag + recent_scheduled** |
| LLM 偷懒重复防护 | 无（nla 反而加剧）| **软护栏（pacing + recent_scheduled），不硬禁** |
| 结构化路径管理 | 尝试用 nla 做（失败）| **明确交给 P3 里程碑层** |
| 设计否决记录 | 无 | **§0.5 保留** |
| **单轮闭环 guard** | 无 | **CS + MA prompt 均补反例表（§2.6 / §3.7）+ 9 条 T7 回归测试** |
| **输入契约文档** | 无 | **`pursuits_input_contract_v1.md` 沉淀** |
| **DB 读路径** | CS-01 / MA-01 / MB-01 写成 tool(SQL) 工具流程 | **全部走 `sys.pursuits_library` 注入**（中控 source=0）；CS-01 改为 if-else 空判；MA-01 / MB-01 改为 code(parse)；`pursuits_lib_exists` / `pursuits_lib_read` 工具登记删除（§7.2）|
| **DB 写路径** | CS-05 / MA-07 / MB-07 写成 tool(SQL) 工具流程 `pursuits_lib_write` | **全部走工作流 END 透传 payload**，中控在回调里 upsert `pursuits_library` 表（§7.6 补中控职责）；CS-04 / MA-06 / MB-06 扩出"组装 new_library"职责；`pursuits_lib_write` 工具登记删除（§7.2）；与 P2 `schedule_timeline` / P3 `future_plan` 写入流程一致 |
| **CS 对话入参** | 无（CS 只吃 lv_1/2/3 + big_event）| **`start.raw_records` ← `sys.baji_records_50`**，CS-02 过滤伪消息后产 `recent_chat_digest` 传给 CS-03 prompt；配套 COLD_START_PROMPT_V2 "对话优先"段（Day 3 落地）|

---

（v3 完，2026-04-21 晚 2 版）
