# 监控池筛选流水线（PIPELINE）

> **目标**：从全市场 78 只公募 REITs + 30+ 只红利 ETF 里，独立筛选出一套有方法论支撑的监控池，替代当前手工挑的 12 只。
>
> **可复跑**：每季度/每年重跑一次，pool 自动更新。
>
> **责任分工**：深度思考由 Opus 写在 methodology/，体力活由 DeepSeek/Node.js 在 scripts/ 执行。

## 流水线

```
┌─────────────────────────────────────────────────────────────────┐
│  Stage 0  策略基线（静态文档）                                       │
│  methodology/00_strategy.md                                      │
│  → 由 Opus 写：投资目标、风险约束、约束 → 决定后续筛选规则的根                │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1  全市场宇宙采集                                            │
│  scripts/01_fetch_universe.mjs                                   │
│  · 拉东方财富 clist 接口：所有 ETF + 所有 REITs                        │
│  · 标准化字段：code, name, market, type, listing_date, aum, fee     │
│  → data/universe.json（约 100 只标的）                              │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2  历史数据采集（每只标的）                                     │
│  scripts/02_fetch_history.mjs                                    │
│  · 拉过去 5 年日线：push2his.eastmoney.com kline                     │
│  · 拉历史分红：fundf10 的 fhsp 接口                                   │
│  · 计算 TTM 分红、3 年股息率均值、最大回撤、年化波动率                       │
│  → data/history.json                                             │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3  量化筛选（按规则过滤）                                       │
│  规则：methodology/02_screening_rules.md（Opus 写）                 │
│  执行：scripts/03_apply_screening.mjs（纯 JS）                       │
│  · 应用硬性门槛（流动性、上市时长、连续分红等）                              │
│  · 按综合评分排序                                                    │
│  → data/screened.json（剩 ~25-30 只 candidates）                    │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4  质量评估（LLM 按 framework 打分）                           │
│  Framework：methodology/04_quality_framework.md（Opus 写）          │
│  执行：scripts/04_review_quality.mjs（DeepSeek API 调用）            │
│  · 对每只 candidate，按 6 维度评分（0-30 分）                          │
│  · 输入：底层资产说明、运营方、近期公告摘要                                │
│  · 输出：每只标的的评分 + 文字理由                                       │
│  → data/quality_scores.json                                      │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  Stage 5  最终池选择（人工或 Opus 把关）                                │
│  · 综合 Stage 3 量化得分 + Stage 4 质量得分                           │
│  · 行业分散约束：每个底层类别 1-2 只                                     │
│  · 总数约束：最终 8-15 只                                            │
│  → data/final_pool.json                                          │
│  → 一键导入 lib/products.ts                                         │
└─────────────────────────────────────────────────────────────────┘
```

## 模型分工

| Stage | 谁做 | 工作内容 |
| --- | --- | --- |
| 0 | 🧠 Opus | 写 strategy.md（投资目标 + 约束）|
| 1 | 🤖 Node.js | 拉数据，无 LLM |
| 2 | 🤖 Node.js | 拉数据 + 计算指标，无 LLM |
| 3 | 🤖 Node.js | 应用规则（规则由 Opus 定义在 02_screening_rules.md）|
| 4 | 🤖 DeepSeek | 按 framework 评分（framework 由 Opus 定义在 04_quality_framework.md）|
| 5 | 🧠 Opus | 最后把关 + 行业分散调整 |

## 运行命令

```bash
# 一次跑完
npm run screen:all

# 分阶段跑
npm run screen:01    # 拉宇宙
npm run screen:02    # 拉历史
npm run screen:03    # 量化筛选
npm run screen:04    # DeepSeek 质量评估（耗时最长，约 5-10 分钟）
npm run screen:05    # 整合最终池

# 导入到 monitor pool
npm run screen:apply # 用 final_pool.json 覆盖 lib/products.ts
```

## 数据契约（Schema）

每个 stage 输出的 JSON schema 在 [methodology/schemas/](schemas/) 里定义，下一阶段严格按 schema 读取。失败的 candidate 不删除，标记 `status: "error"` 留在 JSON 里，便于后续 debug。

## 复跑策略

- **每季度**：重跑 Stage 1-3（基本面变化不大，但价格/分派率会变）
- **每年**：重跑 Stage 4-5（底层资产质量评估更新）
- **触发性**：单只标的有重大公告（扩募、解禁、重大变动）→ 单独重跑该标的的 Stage 4
