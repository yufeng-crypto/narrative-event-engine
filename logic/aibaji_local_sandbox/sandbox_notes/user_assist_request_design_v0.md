# user_assist_request · 角色求助用户机制 · 设计草案 v0

> 📎 **本文档是 [`character_pursuits_design_v0.md`](./character_pursuits_design_v0.md) 节 6.4 的展开**
> 🔧 **在 pursuit 落地阶段中属于 Phase 1.5**（layer3 pursuit 注入之后、M-A 之前）
> ✅ 状态：v0 设计已定稿（7 个决策点 UAR1-UAR7 已有结论，见节 8）

---

## 1. 目标与价值

### 为什么需要

当前 `character_pursuits` 让角色的日程有了自驱感，但推进**完全是角色单方面**的。现实里，人推进一件事时会遇到"这事我一个人拿不准"的卡点，会主动找能帮上忙的人。这个机制补的就是这一块。

### 目标

1. **运营价值**：产生**有合理事由**的 Push 推送（"她在等你帮她选礼服"，而不是"您有新消息"），非骚扰式
2. **活人感价值**：命中"能动性 + 不可预测性"——角色主动发起需求，用户不知道什么时候会有
3. **用户参与价值**：用户在场 / 不在场对角色的推进**真的有差**，而不是"我来不来都一样"

### 成功判据

- P2 生成事件时能稳定产出合格的 `user_assist_request`（一天 1 条、有具体事由、linked_pursuit_id 对得上 top-5），10 次测试里≥8 次合格
- fallback 有**代价感**：用户缺席时，下次对话角色主动提起这件事（而不是假装没发生过）
- 对上限友好：7 天内 UAR 总数可控（默认 ≤ 5 条），不产生 Push 疲劳

---

## 2. 名词与边界

### 名词

- **UAR（user_assist_request）**：一条 schedule event 的附加字段，标记"角色在这条事件里想请用户帮忙"
- **assist_window**：从事件 start_dt 开始的等待用户上线的时间窗（默认 30 分钟）
- **fallback plan**：超时后角色走哪条路径（预存在 event 里，不需要再调 LLM）
- **post_assist_callback**：用户之后上线时，角色要主动提起这件事的钩子

### 边界（什么**不**是 UAR）

- ❌ 剧情关键抉择（"要不要去香港"这种）→ 走 P3 `hook_injection`
- ❌ 日常陪伴话题（"今天好想你"）→ 走 P2-SE 状态展示 或 hook_injection
- ❌ 情绪性求陪伴（"心情不好"）→ 走情绪峰值机制
- ✅ **pursuit 推进过程中，有明确可落地动作、非用户不可的具体协助**（挑衣服、拿主意、帮选酒店、出方案）

### 与 hook_injection 的关系

| 机制 | 事由来源 | 触发载体 | 优先级 | Push |
|---|---|---|---|---|
| **UAR** | **pursuit 推进** | **P2 事件附加字段** | 中 | ✅ |
| hook_injection | P3 叙事节点 | baji_chat_all 对话层注入 | 高 | ✅ |
| P2-SE 展开 | 固定频率 | 状态展示 | 低 | ❌ |

**冲突规则**：同一时刻两者都想触发时，hook_injection 优先（叙事 > 功能）。

---

## 3. Schema

### 3.1 schedule event 扩展字段

在现有 P2-Lite 事件 schema（`description / location / summary / expression / clothing / deepthinking / hook_priority`）基础上新增：

```json
{
  // ... 原有字段
  "linked_pursuit_id": "pur_20260420_002",

  "needs_user_help": true,

  "assist_request": {
    "what_user_can_do": "帮我拿个主意——红色那件稳重，但黑色那件龙哥可能更喜欢",
    "why_user": "龙哥的口味我拿不准，你比我懂他",
    "window_minutes": 30,
    "push_headline": "孟雅在等你帮她选礼服",
    "if_absent_plan": {
      "resolution_type": "self_resolve_with_cost",
      "narrative_self": "最后挑了红色那件，但心里一直犯嘀咕",
      "narrative_callback": "你昨天没回我，我自己挑了红色的，不知道龙哥会不会觉得太扎眼",
      "quality_impact": "partial",
      "progress_note": "独自完成：缺少用户意见，质量打折，心态受影响"
    }
  }
}
```

### 3.2 fallback 的三种 resolution_type

| 类型 | 语义 | pursuit 进度影响 | 叙事回调 |
|---|---|---|---|
| `self_resolve_with_cost` | 自己做了，但留疑虑/质量打折/情绪受影响 | 推进但带"不完美"标签 | ✅ 必须有 narrative_callback |
| `partial_fail` | 非用户不可的事，没做成 | 不推进，可能生成补救事件 | ✅ 必须有 narrative_callback |
| `defer` | 挪到明天同时段再试 | 不推进，P2 下次周期补 | ✅ 必须有 narrative_callback |

**默认使用 `self_resolve_with_cost`**（80% 场景）；`partial_fail` 仅用于"必须用户参与"的事（签字、决定性选择）；`defer` 慎用，最多让同一事 defer 1 次。

### 3.3 为什么 fallback 预存而不是动态重算

- 预存：P2 一次 LLM 调用把 needs_user_help 的事件 + fallback 都吐出来。窗口超时时 **CODE 层直接选 branch**，零额外 LLM 调用
- 动态：窗口超时时再调 LLM 重写事件，灵活但成本翻倍

选预存。如果 MVP 发现 fallback 僵硬再升级动态。

---

## 4. P2 prompt 改造

### 4.1 在哪插入

沿用 `simulate_full_day.py` 的 layer 思想：

- layer1 / layer2 / layer3（pursuit 注入）已存在
- **新增 layer4（UAR 判定块）**：在 layer3 之后

### 4.2 硬约束（必须进 prompt）

```
【角色求助用户的条件】
生成本条事件时，你**可以**标记 needs_user_help=true，但必须同时满足：

1. 本条事件的 linked_pursuit_id 必须是 top-5 中的一条（不能是 top-5 之外的）
2. what_user_can_do 必须写明**具体动作**（"帮我拿主意选 A 还是 B"、"帮我定酒店"），
   **不能**是空话（"需要你的陪伴"、"希望你在"）
3. why_user 必须解释**为什么非用户不可**——
   不是角色自己能搞定，也不是其他 NPC 能替代
4. 本次生成的事件序列里，needs_user_help=true 的**最多只能有 1 条**
5. 时间上避开凌晨 0-8 点（Push 骚扰）
6. 必须同时给出 if_absent_plan，默认选 self_resolve_with_cost

如果没有一件事符合以上条件，**所有事件都写 needs_user_help=false**。
宁可一天零条，不要勉强凑。
```

### 4.3 软建议

- 优先挑 urgency=hard 的 pursuit
- 优先挑 stage 推进到"待决定 / 待确认 / 待选择"的 pursuit（自然卡点）
- window_minutes 默认 30，紧迫事件（hard + span=几天内）可放宽到 60-90

### 4.4 质量测试方案

- 对 mengya 库跑 10 次 layer1_2_3_4，统计：
  - needs_user_help=true 的事件数：期望均值 ≈ 1/day，方差低
  - what_user_can_do 空话率：应 < 20%
  - linked_pursuit_id 越界率：应 = 0%
  - fallback narrative_callback 合理率：人肉 review ≥ 80%
- 若任一指标不达标，迭代 prompt 约束

---

## 5. 时间窗状态机 + fallback

### 5.1 状态机

```
[event.start_dt 到]
    │
    ├── 系统发 Push（headline 从 assist_request.push_headline 取）
    ├── 计时开始：assist_window = window_minutes
    │
[窗内轮询用户状态]
    │
    ├── 有用户消息 → 消费 UAR，走正常 baji_chat_all 流程
    │                  （hook_injection 此时注入 "post_assist_active" 钩子，
    │                   让角色开场就提起这事）
    │
    ├── 点 Push 未对话 → 延长 15min（一次性延长，不叠加）
    │
    └── 窗口超时 → 触发 fallback
                    │
                    ├── resolution_type = self_resolve_with_cost
                    │   ├── event 照旧完成
                    │   ├── M-B 回写 pursuit.progress_log，summary 带 "[SOLO]" 标签
                    │   └── 生成 post_assist_callback 钩子（narrative_callback 内容，
                    │       下次对话开场用）
                    │
                    ├── resolution_type = partial_fail
                    │   ├── event 标记 status=failed
                    │   ├── M-B **不推进** pursuit
                    │   ├── P2 下次周期可生成"再试一次"事件
                    │   └── post_assist_callback 同上
                    │
                    └── resolution_type = defer
                        ├── event 从 schedule_timeline 移除
                        ├── P2 下次周期在同时段补
                        └── post_assist_callback 内容改为"你昨天没回，我今天再试试"
```

### 5.2 post_assist_callback 机制

关键：**用户回来后，角色必须主动提起这事**，否则 UAR 的叙事价值归零。

实现：在 fallback 触发时往 `hook_injection_queue` 推一条特殊类型：
- `hook_type = "post_assist_callback"`
- `priority = "high"`（高于常规 hook_injection）
- `ttl = 24h`（超过 24h 该 callback 降级为普通 progress_log，不再主动提起）

下次用户上线对话时，baji_chat_all 的节点 ⑨（或 P1 入口）优先消费这条 hook，注入到角色开场语里。

### 5.3 fallback 代价感设计

**核心原则**：用户感到"我没回复，她那边是有代价的"。

代价的三档强度：

| 强度 | 场景占比 | 表现 |
|---|---|---|
| 轻度 | 60% | 事情做了，但心里有疑虑 → progress_log 记下"独自完成，感到不确定" |
| 中度 | 30% | 结果打折（礼服选得普通、方案没最优） → pursuit stage 更新时带 "partial" |
| 重度 | 10% | 没做成 / 挪到明天 / 情绪明显受影响 → partial_fail 或 defer |

**强度分布由 LLM 在生成 if_absent_plan 时决定**（prompt 里给一个分布引导），不由 CODE 随机。

---

## 6. 与现有系统的耦合

### 6.1 与 pursuit 库

- UAR 的 `linked_pursuit_id` 必须来自 `pursuits_top5_cache`（不是全库）
- M-B 回写时：
  - 消费型 UAR（用户回了）→ 正常推进 progress_log
  - fallback 型 UAR（用户没回）→ progress_log 加 `[SOLO]` / `[FAILED]` / `[DEFERRED]` 标签，current_stage 带"独自完成但…"的补语

### 6.2 与 P3 hook_injection

- P3 输出的 hook_injection 优先级高于 UAR（叙事 > 功能）
- UAR 触发的 post_assist_callback 和 P3 hook 冲突时，post_assist_callback 延后到下一轮对话（或合并消费，取决于语义兼容性）

### 6.3 与 P2-SE（状态展示）

- 无冲突。UAR 生成在 P2 主链，P2-SE 只展开既有事件
- P2-SE 不负责生成 UAR，也不触发 Push

---

## 7. 落地阶段（UAR 内部子阶段）

> **命名约定**：本节用 Step 0/1/2/3 指代 UAR 内部的实现子阶段，避免和主文档 `character_pursuits_design_v0.md` 的 Phase 1.5 混淆。整个 UAR 开发属于主文档的 **Phase 1.5**。

### Step 0 · 沙盒 MVP（预计 2-3 天）

目标：把链路在沙盒里端到端跑通（模拟用户缺席）。

- [1] **schema 扩展**：event_validator.py 加对 `needs_user_help` / `assist_request` 的校验规则
- [2] **P2 prompt layer4**：在 `simulate_full_day.py` 加 `LAYER4_UAR_INSERT` 块
- [3] **质量测试**：mengya × 10 轮，统计节 4.4 的 4 个指标
- [4] **simulator 加用户缺席模式**：`--simulate-user-absent` 开关，event.start_dt 到期就走 fallback
- [5] **M-B 扩展**：`apply_changes` 识别 fallback 事件的 `[SOLO]` / `[FAILED]` / `[DEFERRED]` 标签
- [6] **post_assist_callback 队列**：落到 `out/hook_queue/` 目录，暂不接回 baji_chat_all

### Step 1 · 沙盒完整端到端（预计 2 天）

- [7] **Push 模拟器**：根据 event.start_dt 往 `out/push_events/` 写推送记录
- [8] **对话回来的 callback 注入**：在主文档 Phase 2（M-A）里消费 post_assist_callback 队列，验证角色开场就提起
- [9] **多 pursuit 库测试**：除 mengya 外再造 1-2 个测试角色，验证泛化

### Step 2 · 线上联调（工程侧，属于主文档 Phase 4）

- Push 平台对接
- 用户在线状态监测
- 窗口延长 / 取消逻辑

### Step 3 · 完整版（前置依赖 NPC 关系库）

- 设计 `character_relations` 库
- fallback 扩展第四分支 `seek_npc_help`
- 相关 NPC 在 progress_log 里被记为协助者

---

## 8. 决策定稿（v0 已确认）

| # | 问题 | 决策 | 备注 |
|---|---|---|---|
| **UAR1** | `assist_window` 时长 | **30 分钟** | 固定值，不设角色/pursuit 粒度差异 |
| **UAR2** | 每日 UAR 上限 | **1 条/天** | 宁可一天零条，不要勉强凑 |
| **UAR3** | 7 天滚动上限 | **3 条/周** | 控 Push 疲劳 |
| **UAR4** | 多候选 pursuit 时排序 | **stage 卡点优先**（用户协助能直接解锁下一步的 pursuit） | 比 urgency 优先更贴近"何时真需要用户" |
| **UAR5** | ~~长期缺席 UAR 累积~~ | **撤销**（问题描述不准确） | UAR 每条独立 30min fallback，不存在累积；callback 的 24h TTL 自然衰减 |
| **UAR6** | `post_assist_callback` TTL | **24h** | 超时降级为 progress_log 里的 `[SOLO]` 标签，角色不主动说起但"记得" |
| **UAR7** | 代价强度分布（轻 60/中 30/重 10）是否 CODE 强制 | **MVP 阶段不强制** | 先跑 10 次看 LLM 自然分布；若全压轻度再加 7 天窗口监测强制下一条走中/重度 |

**决策原则**：能用 prompt 约束 + 测试迭代解决的，不加 CODE 层硬规则；CODE 层硬规则只留给 LLM 反复测试失控的地方（如 UAR7 的 fallback 机制）。

---

## 9. 附录 · 一个完整示例

**场景**：孟雅的 top-1 pursuit 是"陪龙哥去香港拍卖会"，stage="已选好服装，待与龙哥沟通配合细节"。

**P2 在 16:00 时段生成的事件**：

```json
{
  "start_dt": "2026-04-20T16:00:00",
  "end_dt": "2026-04-20T17:00:00",
  "location": "港湾卧室",
  "description": "试穿两件拍卖会备选礼服，对着镜子比较",
  "summary": "试穿礼服拿主意",
  "expression": "纠结",
  "clothing": "黑色礼服",
  "deepthinking": "红色那件稳重，但黑色显气场，龙哥那边到底会更喜欢哪件...",
  "hook_priority": 7,

  "linked_pursuit_id": "pur_20260420_002",
  "needs_user_help": true,
  "assist_request": {
    "what_user_can_do": "帮我拿个主意——红色稳重还是黑色显气场，哪件适合拍卖会场合",
    "why_user": "龙哥的口味我拿不准，你比我了解他",
    "window_minutes": 30,
    "push_headline": "孟雅在等你帮她选礼服",
    "if_absent_plan": {
      "resolution_type": "self_resolve_with_cost",
      "narrative_self": "最后挑了黑色那件，但一直觉得是不是太显眼了",
      "narrative_callback": "昨晚你没回我，我自己挑了黑色那件...不知道龙哥会怎么想。你现在看还来得及换吗？",
      "quality_impact": "partial",
      "progress_note": "[SOLO] 独自选定礼服，缺少用户意见，对结果不自信"
    }
  }
}
```

**用户响应路径**：

- **30min 内回复**：对话开场，角色直接问"红色还是黑色，帮我决定一下"；pursuit 推进正常，stage 更新为"已选定礼服"
- **30min 超时**：
  - event 照旧完成，`[SOLO]` 标签写入 progress_log
  - pursuit current_stage 变为"独自选定黑色礼服，心里没底"
  - post_assist_callback 入队
  - 用户下次上线（比如第二天早上）对话开场，角色主动说出 narrative_callback

**pursuit 库变更**：

```
progress_log 新增：
  {
    "ts": "2026-04-20T17:00:00+08:00",
    "summary": "[SOLO] 独自选定黑色礼服，缺少用户意见",
    "event_refs": [...],
    "uar_fallback": "self_resolve_with_cost"
  }

current_stage：
  "已选好服装，待与龙哥沟通配合细节"
  -> "独自选定黑色礼服但心里没底，待与龙哥沟通 + 希望用户补确认"
```

---

## §A UAR 工程层补充：sys.* 变量清单 + 缓存 key 清单（v0.1, 2026-04-21 补）

> 本节对 §2.4 / §2.5 做工程层细化，格式对齐 `pursuits_workflow_inventory_v3.md §7.1 / §7.3`。
> 不改 v0 主体；仅作为 UAR 落地前的"中控注入 + 缓存读写"对接清单。
> 列出的项**只针对 UAR 自己的 4 个缓存**，与 pursuits 主库 (`pursuits_library`) 的 `assist_request_history` DB 列**独立**（见末段说明）。

### A.1 UAR 新增 sys.* 变量（中控 source=0 注入给工作流）

| sys.* | 去向（工作流 / 节点） | 来源（中控怎么拿） | 类型 | 是否可空 | 备注 |
|---|---|---|---|---|---|
| `sys.active_uar_raw` | **baji_chat_all 起点**（消费 UAR）/ 未来 UAR 回放工作流 | 中控读缓存 `active_uar`（dim = `sharedVariable:{member_id}:{user_id}`），若 TTL 未到且未结算则注入 JSON 字符串；否则注入 `""` | string (JSON 对象序列化) | 可空（`""` 表示当前无活跃 UAR） | 工作流内用 code 解析；**禁止**在工作流内再去读缓存（v3.2 §0.2：读 DB/缓存唯一路径=sys 注入）|
| `sys.uar_daily_count_raw` | **M-B 生成 UAR 前的限流判断节点**（UAR2：日上限 1 条）| 中控读缓存 `uar_daily_count`，未命中注入 `0` | int | 不可空（缺省 `0`） | M-B 生成前读此值 == 0 才允许产出 `needs_user_help=true`；==1 则本日跳过 |
| `sys.uar_weekly_count_raw` | **M-B 生成 UAR 前的限流判断节点**（UAR3：7d 上限 3 条）| 中控读缓存 `uar_weekly_count`，未命中注入 `0` | int | 不可空（缺省 `0`） | 同上；同时满足 daily==0 **且** weekly<3 才产出 UAR |
| `sys.post_assist_callback_queue_raw` | **baji_chat_all 起点**（消费 callback）| 中控读缓存 `post_assist_callback_queue`，未命中注入 `"[]"` | string (JSON array 序列化) | 不可空（缺省 `"[]"`） | 起点 code 节点 FIFO 消费一条；消费后由同工作流 variable-assigner 覆写回去 |
| `sys.last_uar_ref_raw` | **M-B Fallback 检查节点**（MB-UAR-FALLBACK-00） | 中控读缓存 `last_uar_ref`，未命中注入 `""` | string (JSON 对象序列化) | 可空（`""` 表示最近 24h 未产过 UAR）| 方案 B：用来给 MB 判"是否有需要 fallback 的超时 UAR"；见 §B.4.1 |

> **未列出**：UAR 自产自销的内部产物（如 M-B 节点 LLM 返回的 `assist_request` 对象、`if_absent_plan` 等）由工作流内部 variable-assigner 写入缓存，**不**需要中控预注入，故不出现在本表。

### A.2 UAR 新增缓存 key（工作流用 variable-extractor / variable-assigner 自己读写）

维度默认 = `sharedVariable:{sys.member_id}:{sys.user_id}`（沿用线上约定；`assigned_variables = [sys.user_id, sys.member_id]`）。TTL 采用 Dify `expired_time: [H, M, S]` 元组。

| 维度 dim | key | TTL | 写入方 | 读取方 | 结构 | 备注 / 冲突规则 |
|---|---|---|---|---|---|---|
| `sharedVariable:{member_id}:{user_id}` | `active_uar` | `[0, 30, 0]`（30min；对齐 UAR1 `assist_window`；**TTL 行为联调前先抓一条 trace 验证**，见 §A.4 已决点 #2） | **M-B 生成节点**（LLM 判 `needs_user_help=true` 时 over-write） | baji_chat_all 起点（消费后 over-write 为 `""` 或整 key 删除）| JSON object，字段 = §3.1 `assist_request` 全集：`what_user_can_do / why_user / window_minutes / push_headline / if_absent_plan{resolution_type, narrative_self, narrative_callback, quality_impact, progress_note} / linked_pursuit_id / linked_event_id / created_at / deadline_at` | **冲突规则**：同时只允许 1 条活跃 UAR；M-B 写入前若检测到 `active_uar` 非空则**跳过**本次写（Prompt 层 UAR2 已保证日上限 1 条，一般不会撞；兜底仍以 daily_count 限流为主）。TTL 到期未被消费 → 自然失效 + 下次 MB 跑时通过 `last_uar_ref` 做 fallback（见 §B.2 方案 B）。|
| `sharedVariable:{member_id}:{user_id}` | `uar_daily_count` | `[23, 59, 59]`（当日归零；**次日首次 M-B 执行时由 over-write 覆盖刷新**，与线上 `schedule_timeline` 同款"日级"TTL）| M-B 生成节点（产出 UAR 后 +1 over-write）；每天首次 M-B 跑时若读到未命中则以 `0` 起算 | M-B 限流判断（生成前读）；P2 改造节点（若需要展示限流状态）| int（0 or 1） | **冲突规则**：值==1 时 M-B **不**再产出 UAR（prompt 层 + code 层双保险）；日首次 M-B 若读到前一日残留值，直接 over-write `0`（不依赖 Dify TTL 精确归零）。命名统一为 `uar_daily_count`（见 §A.4 已决点 #1；同步 `pursuits_workflow_inventory_v3.md §7.3`）。|
| `sharedVariable:{member_id}:{user_id}` | `uar_weekly_count` | `[167, 59, 59]`（7d，等同线上 `future_plan` 的周级 TTL）| M-B 生成节点（产出 UAR 后 +1 over-write）| M-B 限流判断（生成前读）| int（0..3） | **冲突规则**：值>=3 时 M-B **不**再产出 UAR（UAR3 硬上限）。**MVP 接受非严格滑动窗的近似误差**（见 §A.4 已决点 #3）；若后期 push 疲劳数据不佳再升级为 array-of-timestamps + code 裁剪。|
| `sharedVariable:{member_id}:{user_id}` | `post_assist_callback_queue` | `[23, 59, 59]`（24h；对齐 UAR6：超时降级为 `progress_log` 里的 `[SOLO]` 标签，不再主动提起）| M-B Fallback 节点（MB-UAR-FALLBACK-00，见 §B.4.1；窗口超时时 append 一条）；baji_chat_all 消费节点（消费后 over-write 剩余）| baji_chat_all 起点 code 节点（FIFO 取 head，注入到开场语）| JSON array，每条 record：`{hook_type: "post_assist_callback", uar_id, linked_pursuit_id, narrative_callback, priority: "high", enqueued_at, ttl_hours: 24}` | **冲突规则**：同一 `uar_id` 只入队 1 次（写入前按 `uar_id` 去重）。超过 TTL 未消费 → 自然失效；pursuits_library.progress_log 里 `[SOLO]/[FAILED]/[DEFERRED]` 标签作为"记得但不再主动提起"的长期残留（由 DB 侧 `assist_request_history` 审计）。与 P3 `hook_injection_queue` 是**两个独立队列**，优先级规则见 §6.2。|
| `sharedVariable:{member_id}:{user_id}` | `last_uar_ref` **（方案 B，新增）** | `[24, 0, 0]`（24h；盖住 MB 最长触发周期 ~2h × 若干倍）| M-B 生成节点（产出 UAR 时与 `active_uar` 同步 over-write）| **M-B Fallback 检查节点**（MB-UAR-FALLBACK-00）；中控 source=0 注入 `sys.last_uar_ref_raw` | JSON object，字段同 `active_uar`（`assist_request` 全集，含 `uar_id` / `deadline_at` / `if_absent_plan` 等）| **用途**：给下次 MB 判断"是否有 UAR 未结算但已超时需 fallback"。判定逻辑见 §B.2 方案 B：last_uar_ref 存在 + active_uar 空 + history 无结算记录 → fallback。**不污染 DB**，不与 `assist_request_history` 列挂钩。**冲突规则**：下次产新 UAR 时直接 over-write（不做历史累积；只记录"最近一条"）；MB fallback 处理完成后由 variable-assigner 清空；MA 结算清理不强制（MB 自己会判 history 已结算 → 跳过 fallback）。|

### A.3 说明：为什么 UAR 缓存 5 项全不走 DB

UAR 的 5 项缓存（`active_uar` / `uar_daily_count` / `uar_weekly_count` / `post_assist_callback_queue` / `last_uar_ref`）**全部只落 Dify cache**，不进 DB 表。和 pursuits v3.2 的 `pursuits_library.pursuits_json` / `pursuits_library.assist_request_history` 列**并行但解耦**：前者是高频短期状态（30min ~ 7d TTL，自然失效 / 每日 over-write 刷新 / 单条 over-write），命中即用、过期即弃，不需要长期可查；后者是 UAR 生命周期结算后的审计尾巴（90 条 / 180 天），做回放和离线审计。DB 持久化**只要** `assist_request_history` 一份审计记录就够了，无需把限流计数器 / 活跃态 / pending 引用也冗余落表。

**特别说明 `last_uar_ref`（方案 B）**：这是把"UAR pending 态"留在缓存而**不**立刻写 DB 的核心承载。把 pending 写进 `assist_request_history` 会带来 4 个弊端：
- **双写一致性**：缓存写 `active_uar` 与 DB 写 `assist_request_history(pending)` 无事务原子性，任一侧失败则状态漂移，修复逻辑复杂。
- **DB 写放大**：UAR 生成节点每次跑都要多 1 次 DB 写；90% 情况下 pending 会被 30min 内的 MA 结算覆盖，这笔 pending 写是纯开销。
- **history 语义稀释**：`assist_request_history` 从"已结算 / 已 fallback 的审计尾巴"变成"含运行态的状态机"，读取方要先按 resolution_type 过滤，语义分层被破坏。
- **END payload 膨胀**：MB END 要带上 "本次写了一条 pending" 的元信息给中控回调，增加序列化体积和接口耦合。

用 `last_uar_ref` 缓存承载 pending 则无此 4 弊：**生成**时 MB 同步写 `active_uar` + `last_uar_ref`；**消费**时 MA 判 `resolved=true` 则清 `active_uar` + 写 `assist_request_history(resolved)`（此时 `last_uar_ref` 仍留着，次日 MB 通过 history 已结算判定跳过 fallback）；**超时**时下次 MB 跑到 Fallback 节点，读 `sys.last_uar_ref_raw` + `active_uar` 空 + history 无结算记录 → 触发 fallback，写 `assist_request_history(fallback)` + `post_assist_callback_queue`，随后清 `last_uar_ref`。

**代价**：接受"灰色窗口"——UAR 超时到下次 MB 运行之间（最坏 ≈ 2h，MB cron 周期），fallback 的 `post_assist_callback` 入队存在延迟。对 UAR 场景可接受（用户下次上线前 MB 已跑过，callback 已入队，用户感知无损）。

---

### A.4 阅读时发现的冲突点（**已决，2026-04-21**）

1. **`uar_daily_count` vs `uar_daily_counter` 命名不一致**（已决）：统一为 **`uar_daily_count`**；`pursuits_workflow_inventory_v3.md §7.3` 同步改名。
2. **`active_uar` 30min TTL 语义待验**（已决）：按 **`[0, 30, 0]` = 30min** 登记；**联调前抓一条 trace 验证**，若实测非 30min 则退化为 `[1, 0, 0]` 并由 MB Fallback 节点（非 cron）裁剪。选项 (a)。
3. **`uar_weekly_count` 非严格滑动窗**（已决）：**MVP 接受 `[167,59,59]` 整体过期归零的近似误差**；若后期 Push 疲劳数据不佳再升级为 `array-of-timestamps` + code 裁剪。
4. **UAR Fallback 机制**（2026-04-21 新决，原 §B.7 问题）：**不引入独立 cron**，用 **MB-driven fallback**（方案 B）——下次 MB 运行时自检 `sys.last_uar_ref_raw` 判是否需补发 callback。接受 ≤2h 灰色窗口。详见 §A.3 / §B.2 / §B.4.1。
5. **UAR pending 是否立刻写 DB**（2026-04-21 新决）：**不写**。pending 态只留缓存 `last_uar_ref`；`assist_request_history` 仅在 resolved / fallback 时写入，保持"审计尾巴"语义。详见 §A.3 "特别说明"段。

---

## §B UAR 工作流分工图（v0.1, 2026-04-21 补）

> 本节回答："UAR 到底要新增几个 Dify 工作流？每条路径（生成 / 消费 / 结算 / fallback）
> 挂在哪里？" 配套 §A（sys.*/缓存表）+ `pursuits_workflow_inventory_v3.md §7`。

### B.1 TL;DR

- **新增 Dify 工作流数量 = 0**。UAR 的生成 / 消费 / 结算 / fallback 全部**嫁接**到现有三条链路：
  - 生成 → P2-MB（`pursuits maintain_after_schedule`）
  - 消费 → baji_chat_all 起点 code 节点
  - 结算 → P1-MA（`pursuits maintain_after_chat`）
  - **Fallback → P2-MB 自检节点（MB-UAR-FALLBACK-00）**，依赖 `last_uar_ref` 缓存 + `assist_request_history` DB 比对（方案 B，§A.4 已决点 #4）
- **新增中控 cron = 0**（原设计有 1 条 UAR 超时 cron，已在 2026-04-21 撤销；改由 MB-driven fallback 承担，接受 ≤2h 灰色窗口）。
- **新增 DB 列 = 0**（`pursuits_library.assist_request_history` 已在 v3 inventory §7.4.3 定义）。

### B.2 四条路径 vs 现有挂载点

| 路径 | 触发时机 | 挂到哪里 | 核心动作 | 涉及 sys.* / 缓存 key |
|---|---|---|---|---|
| **生成** | schedule_timeline 生成后（P2-Lite END 回调触发 MB） | **P2-MB** 新增第 4 桶 `new_uars`（LLM）+ 限流 code + variable-assigner | LLM 判"需要用户帮忙" → CODE 读 daily/weekly 计数做限流 → 通过则写 `active_uar` + count+=1 | 读：`uar_daily_count_raw` / `uar_weekly_count_raw`；写：`active_uar` / `uar_daily_count` / `uar_weekly_count` |
| **消费** | 用户打开对话（baji_chat_all 起点） | **baji_chat_all 起点 code 节点**（扩展）| 解析 `active_uar` + `post_assist_callback_queue` → 拼 `uar_context_block` 注入 system prompt；FIFO 消费 1 条 callback | 读：`active_uar_raw` / `post_assist_callback_queue_raw`；写：`post_assist_callback_queue`（剔除 head 后 over-write） |
| **结算** | 对话结束后（baji_chat_all END 回调触发 MA）| **P1-MA** 新增第 8 桶 `uar_resolution`（LLM）+ 结算 code | LLM 判用户本轮是否响应了活跃 UAR → CODE 清 `active_uar` + 往 END payload 带 `uar_resolution` 字段 → 中控 upsert `assist_request_history` | 读：`active_uar_raw`；写：`active_uar`（清空）；DB 写：`pursuits_library.assist_request_history` |
| **Fallback** | P2-MB 自检节点（每 MB 周期 ≈ 2h 一次，即下次 MB 生成 schedule_timeline 时顺手跑） | **P2-MB 入口新增 MB-UAR-FALLBACK-00 节点**（在 MB-LLM 之前） | 读 `sys.last_uar_ref_raw` + `sys.active_uar_raw` + 内部查 `assist_request_history`：若 `last_uar_ref` 非空 + `active_uar` 空 + history 无对应 uar_id 的结算记录 → 认定超时未结算 → 写 `post_assist_callback_queue` append + DB 写 `assist_request_history(resolution_type=fallback)` + 清 `last_uar_ref` | 读：`last_uar_ref_raw` / `active_uar_raw`；写：`post_assist_callback_queue` / `last_uar_ref`（清空）；DB 写：`pursuits_library.assist_request_history` |

### B.3 为什么不独立 UAR 工作流 / 也不加 cron

1. **UAR 状态机简单**：`generate → active → (consume | fallback) → history`，不需要独立编排图。
2. **上下文复用**：生成时 MB 已有 `pursuits_library + schedule_timeline` 在手；结算时 MA 已有 `pursuits_library + chat transcript` 在手。独立工作流等于复制这堆 sys.* 入参。
3. **运维成本**：Dify 工作流每多一个 → 多一份线上 trace / 限流 / 监控成本；能嫁接就不要新建。
4. **Fallback 不走 cron**（2026-04-21 决）：时间触发确实 ≠ 用户动作触发，但 UAR 场景下**下次 MB 必然在 ~2h 内跑**（schedule_timeline 的正常刷新节拍），顺手做 fallback 自检足够覆盖"用户下次上线前 callback 已入队"的体验要求。cron 的价值仅在"秒级精准触发"，UAR 不需要——接受 ≤2h 灰色窗口，换来：**零新 cron / 零新进程 / 零独立脚本**，所有 UAR 状态流转都在 MB 一个工作流里闭环。详见 §A.4 已决点 #4。

### B.4 三条现有工作流的节点增量清单

> 格式对齐 `pursuits_workflow_inventory_v3.md §2/§3/§4` 的节点表。**待定稿**：这里只列增量位置 / 职责，具体节点 id 与 edge 连线留给 v3.3 落实（D1 后续执行）。

#### B.4.1 P2-MB 增量（在 `pursuits_workflow_inventory_v3.md §4` 基础上加）

| 节点 | 类型 | 增量点 | 动作 |
|---|---|---|---|
| **MB-UAR-FALLBACK-00**（新） | code | **MB 入口**，在原 MB-01（空库判定）之前或并列 | 读 `sys.last_uar_ref_raw` / `sys.active_uar_raw` + 查 `assist_request_history`（从 `sys.pursuits_library_raw` 解析）：若满足 `last_uar_ref` 非空 **且** `active_uar` 空 **且** `history` 内无对应 `uar_id` 的结算记录 → 触发 fallback 分支：append 一条 `post_assist_callback` 入队；END payload 额外带 `uar_fallback_fired: {uar_id, resolution_type: "fallback", resolved_at, progress_note}`（中控据此 upsert `assist_request_history`）；最后 variable-assigner 清空 `last_uar_ref`。若不满足则 noop 直通。**本节点不调用 LLM**。 |
| MB-LLM（prompt） | LLM | prompt 加 §5 `new_uars` 桶 | 输出 `{needs_user_help, assist_request: {what_user_can_do, why_user, window_minutes, push_headline, if_absent_plan{...}, linked_pursuit_id, linked_event_id}}`；字段对齐 §3.1 |
| MB-UAR-01（新） | code | MB-LLM 之后、MB-06 之前 | 读 `sys.uar_daily_count_raw` / `sys.uar_weekly_count_raw`；daily==0 && weekly<3 则放行，否则丢弃本条 UAR |
| MB-UAR-02（新） | variable-assigner | MB-UAR-01 之后 | over-write：`active_uar` ← assist_request JSON；`last_uar_ref` ← 同份 assist_request JSON（方案 B，盖住 MB 周期用于 fallback 自检）；`uar_daily_count` ← +1；`uar_weekly_count` ← +1 |
| MB-END payload | end | 扩 | 新增 `uar_created: bool` / `uar_id: str` / `uar_fallback_fired: dict \| null` 三字段；中控埋点用（`uar_fallback_fired` 非空时 upsert `assist_request_history`）|

#### B.4.2 baji_chat_all 增量（P1 既有工作流，不在 pursuits_workflow_inventory_v3 内）

| 节点 | 类型 | 增量点 | 动作 |
|---|---|---|---|
| 起点 code 节点 | code | 入口扩展 | 解析 `sys.active_uar_raw` + `sys.post_assist_callback_queue_raw`；拼 `uar_context_block`（UAR 正文 + 首条 callback）注入 system prompt；FIFO 取 callback head |
| 消费后 variable-assigner | variable-assigner | 起点 code 之后 | over-write `post_assist_callback_queue` ← 剔除 head 后的剩余数组（active_uar 不清空 —— 清空由 MA 结算或 cron 做）|

#### B.4.3 P1-MA 增量（在 `pursuits_workflow_inventory_v3.md §3` 基础上加）

| 节点 | 类型 | 增量点 | 动作 |
|---|---|---|---|
| MA-LLM（prompt） | LLM | prompt 加第 8 桶 `uar_resolution` | 基于 `sys.active_uar_raw` 判用户本轮是否响应：`{resolved: bool, resolution_type: "user_helped"\|"user_declined"\|"pending", evidence_message_ref, progress_note}` |
| MA-UAR-01（新） | code | MA-LLM 之后、MA-06 之前 | 若 `resolved=true`：清 `active_uar`；若响应带 `progress_note`：append 到对应 pursuit 的 `progress_log`（tag = `uar_resolved`） |
| MA-END payload | end | 扩 | 新增 `uar_resolution: dict \| null` 字段；中控据此 upsert `assist_request_history` DB |

#### B.4.4 ~~中控 Fallback Cron~~（**已撤销，2026-04-21**）

> 原设计此处有一条 `tools/uar_fallback_cron.py` 每 5min 扫 `active_uar.deadline_at` 的 cron 脚本。**已撤销**，改由 B.4.1 的 `MB-UAR-FALLBACK-00` 节点承担（方案 B，见 §A.4 已决点 #4）。零新 cron、零新进程。

### B.5 与 §A 表的一致性检查

| §A sys.* / cache key | §B 哪条路径 | 写入挂载点 | 读取挂载点 | 一致性 |
|---|---|---|---|---|
| `sys.active_uar_raw` ↔ `active_uar` | 生成 / 消费 / 结算 | MB-UAR-02（生成）；MA-UAR-01（结算清空）| baji_chat_all 起点；MA-UAR-01；MB-UAR-FALLBACK-00（读判空）| ✓ |
| `sys.uar_daily_count_raw` ↔ `uar_daily_count` | 生成限流 | MB-UAR-02（+1）| MB-UAR-01 | ✓ |
| `sys.uar_weekly_count_raw` ↔ `uar_weekly_count` | 生成限流 | MB-UAR-02（+1）| MB-UAR-01 | ✓ |
| `sys.post_assist_callback_queue_raw` ↔ `post_assist_callback_queue` | fallback → 消费 | MB-UAR-FALLBACK-00（append）；baji_chat_all 消费后（剔除 head）| baji_chat_all 起点 | ✓ |
| **`sys.last_uar_ref_raw` ↔ `last_uar_ref`**（方案 B）| fallback 自检 | MB-UAR-02（生成时同步写）；MB-UAR-FALLBACK-00（处理完清空）| MB-UAR-FALLBACK-00 | ✓ |
| DB `pursuits_library.assist_request_history` | 结算 / fallback（**不含 pending**）| 中控（MA-END 回调带 `uar_resolution`）；中控（MB-END 回调带 `uar_fallback_fired`）| 客户端审计 / 回放；MB-UAR-FALLBACK-00 读判"是否已结算" | ✓ |

### B.6 MVP 范围外（Phase 2 再议）

1. **回放工作流**：如果未来要做"角色主动回顾过去 UAR 轨迹"功能，需要新增一条独立工作流读 `assist_request_history` 做 aggregation；MVP 不做。
2. **UAR chain / dependency**：当前一次只允许 1 条活跃 UAR；未来若做"UAR 链路（上次回应后派生下一条）"，需要在 MB-UAR-02 之前加 `previous_uar_context` 上下文拼接；MVP 不做。
3. **多渠道 push**：push_headline 只是 field，实际 push 通道（APP 内通知 / 短信）在中控侧决定；UAR 工作流层面不管。

### B.7 未决点（**已决，2026-04-21**）

1. **MA prompt 第 8 桶 vs 独立工作流**（已决）：**merge 进 MA**（节约工作流数量；MA 已 7 桶，加 1 到 8 桶在可控范围）。若后续 MA quality test 显示 8 桶导致 LLM 出错率上升再拆；MVP 不预拆。
2. **~~Cron 频率~~**（已撤销）：原问题基于"UAR 超时 cron"前提，该 cron 已撤销（见 §A.4 已决点 #4）。替代方案：**MB-UAR-FALLBACK-00 节点**在每次 MB 运行时（~2h 周期）自检 `last_uar_ref`。`[0,30,0]` TTL 若实测无效则退化为 `[1,0,0]` 并由 MB Fallback 节点裁剪（见 §A.4 已决点 #2）。
3. **`assist_request_history` 清理策略**（已决）：由 **MA-UAR-01 顺手裁剪**（每次结算后保留最新 90 条；180 天外的丢弃）；MB-UAR-FALLBACK-00 写入 fallback 记录时不做裁剪（避免并发写冲突，让 MA 统一收口）。
4. **结算失败兜底**（已决）：若 MA LLM 判 `resolved=false`（用户没响应也没拒绝），**`active_uar` 留着**（等 TTL 自然过期）；MA 只负责"能确认的 resolution"；后续 fallback 由 **MB-UAR-FALLBACK-00** 判定（`last_uar_ref` 非空 + `active_uar` 空[TTL 过期后] + history 无结算记录 → fallback）。
5. **UAR pending 是否立刻写 DB**（已决）：**不写**，只留缓存 `last_uar_ref`。详见 §A.3 "特别说明"段 + §A.4 已决点 #5。接受 ≤2h 灰色窗口。

---
