# Stage 3 · 量化筛选规则

> 输入：`data/history.json`（Stage 2 输出）
> 输出：`data/screened.json`
> 执行：`scripts/03_apply_screening.mjs`（纯 JS，不调 LLM）

## 设计原则

1. **硬门槛先**：不满足的直接淘汰，避免后续浪费 LLM tokens
2. **软评分后**：通过硬门槛的，按多因子综合打分排序
3. **每条规则有理由**：不写"because Gemini said"，每条规则注明来自策略基线（00_strategy.md）的哪条约束
4. **保守优于激进**：宁可漏掉好标的，不要选错标的
5. **可解释**：输出 `passed_rules` / `failed_rules` 字段，让人能 debug 为什么某只被淘汰

## 红利 ETF 筛选规则

### 硬门槛（任一未通过 → 淘汰）

| ID | 规则 | 阈值 | 来源 |
| --- | --- | --- | --- |
| `ETF-H1` | 上市时长 | ≥ 3 年 | 策略 §风险约束: 不足 1 年淘汰；这里加严到 3 年是因为红利 ETF 需要看 3 年股息率均值才有意义 |
| `ETF-H2` | 基金规模 (AUM) | ≥ 10 亿 | 策略 §流动性约束: 太小的 ETF 流动性差、容易合并/清盘 |
| `ETF-H3` | 连续分红年数 | ≥ 2 年 | 策略 §风险约束: 连续 2 年未分红淘汰 |
| `ETF-H4` | 管理费率 | ≤ 0.6% | 长期持有 13 年，每年 0.6% vs 0.2% 复利差距 ~10% 本金。同类有低费率版的优先 |
| `ETF-H5` | 最近 3 年最大回撤 | ≤ 30% | 策略 §13 年累计本金回撤上限 30% |
| `ETF-H6` | 跟踪误差（年化） | ≤ 1.5% | 反映管理质量。误差太大说明运营有问题 |
| `ETF-H7` | 当前 TTM 股息率 | ≥ 3% | 低于 3% 的"红利 ETF"名不副实 |

### 软评分（通过硬门槛后，加权打分排序）

| 维度 | 权重 | 计算方式 |
| --- | --- | --- |
| 当前 TTM 股息率 | 30% | (yield - 3) / (8 - 3) × 100，clamped 0-100 |
| 3 年股息率均值 | 20% | 同上，看长期分红能力 |
| 规模（AUM） | 15% | log10(aum / 10亿) × 25，越大越好（流动性 + 不会清盘） |
| 管理费率（反向）| 10% | (0.6 - fee) / (0.6 - 0.15) × 100 |
| 最大回撤（反向）| 15% | (30 - drawdown) / (30 - 5) × 100 |
| 跟踪误差（反向）| 10% | (1.5 - error) / 1.5 × 100 |

总分 100，前 8 名进入 Stage 4。

## 公募 REITs 筛选规则

> REITs 整体年轻（最早 2021-06），规则比 ETF 更宽松，但增加底层资产维度的硬门槛。

### 硬门槛

| ID | 规则 | 阈值 | 来源 |
| --- | --- | --- | --- |
| `REIT-H1` | 上市时长 | ≥ 1.5 年 | REITs 历史短，不能要求 3 年；但至少要看到 1 个完整年度的运营数据 |
| `REIT-H2` | 基金规模 | ≥ 10 亿 | 策略 §流动性约束 |
| `REIT-H3` | 距上次分红 | ≤ 12 个月 | 策略 §风险约束: 连续不分红淘汰；REITs 法律要求 90% 分红，超过 1 年没分红极端异常 |
| `REIT-H4` | 类型分类 | 必须属于：消费/保租房/能源/交通/物流/园区/市政 之一 | 排除"杂项 REIT"和不熟悉的资产类型 |
| `REIT-H5` | 最近 3 季 NOI 趋势 | 不能连续 3 季下跌 > 5% | 底层资产现金流恶化的早期信号 |
| `REIT-H6` | 战略配售解禁压力 | 未来 6 个月解禁占比 ≤ 30% | 大量解禁会显著压价。注意但不一票否决，因为可能反而是建仓机会 |
| `REIT-H7` | 当前分派率 | ≥ 3.5% | 低于这个的 REIT 价格已经跑得太离谱，不值得加入监控池 |

> H6 处理：解禁占比 30-50% 的 → 标记 `flag: "post-unlock-opportunity"`，进入 Stage 4 但加注；> 50% → 暂时淘汰，下一季度重看。

### 软评分

| 维度 | 权重 | 计算方式 |
| --- | --- | --- |
| 当前分派率 | 25% | (yield - 3.5) / (8 - 3.5) × 100，clamped 0-100 |
| TTM 分派率历史分位 | 20% | 在自己上市以来历史的百分位（90% 分位 = 100 分；50% 分位 = 50 分） |
| P/NAV 折溢价 | 20% | 折价 -10% → 100 分；溢价 0% → 60 分；溢价 +30% → 0 分 |
| 规模 | 10% | log10(aum / 10亿) × 25 |
| 分红频率 | 10% | 4 次/年 → 100；3 → 75；2 → 50；1 → 25 |
| 管理人评级（央企 > 头部基金 > 其他）| 15% | 央企 100；头部 75；其他 50；新管理人 25 |

> 历史分位是关键：避免在历史低位（分派率最低、价格最高）建仓，这个比绝对阈值更精准。

## 综合排名 + 行业约束

通过软评分后：

1. **每个 REIT 子类型保留 Top 2**（消费/保租房/能源/交通/物流 各 2 → 最多 10 只）
2. **A 股红利 ETF 保留 Top 3**
3. **港股红利 ETF 保留 Top 1**
4. **总数上限 14**（dashboard 视觉容量限制）

最终给 Stage 4（DeepSeek 质量评估）的 candidate 数量：14 只左右。

## 输出 schema

```ts
interface ScreenedCandidate {
  code: string;
  name: string;
  category: 'dividend_etf_a' | 'dividend_etf_hk' | 'reit';
  reit_subtype?: 'consumption' | 'rental_housing' | 'energy' | 'transportation' | 'logistics' | 'park' | 'municipal';
  hard_gates_passed: string[];   // ['ETF-H1', 'ETF-H2', ...]
  hard_gates_failed: string[];   // 空数组 = 全过
  score_breakdown: {
    yield: number;
    historical_percentile?: number;
    premium_discount?: number;
    aum: number;
    fee?: number;
    drawdown?: number;
    tracking_error?: number;
    dividend_frequency?: number;
    manager_rating?: number;
  };
  total_score: number;       // 0-100
  rank_in_category: number;  // 类型内排名
  flags: string[];           // 例如 ['post-unlock-opportunity']
  passed_to_stage4: boolean;
}
```

## 不放在这层做的事

- **不做主观质量判断**（如"这家管理人靠不靠谱"）→ Stage 4
- **不做底层资产细节研究**（"这个商场的客流量怎么样"）→ Stage 4
- **不做政策风险预测** → Stage 4
- **不做最终选品决策** → Stage 5

这层是**机械的、可重复的、可解释的**过滤。
