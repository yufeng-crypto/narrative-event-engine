# Stage 4 · 资产质量评估 Framework

> 输入：`data/screened.json`（Stage 3 输出，~14 只 candidates）
> 输出：`data/quality_scores.json`
> 执行：`scripts/04_review_quality.mjs`（DeepSeek API 调用，每只标的一次）

## 目的

量化筛选只能看"过去的数字"，看不到"未来的风险"。Stage 4 用 LLM 读公开公告/年报/新闻，从 6 个定性维度打分。

## 6 维度评分体系

每维度 0-5 分，总分 30 分。每个分值都有锚定描述（anchor），LLM 必须引用具体证据，不能空打分。

### 维度 1：底层资产质量（asset_quality）

> 这只 REIT/ETF 的底层资产本身好不好？

**ETF 适用**（指数成分股质量）：
- 5 分：跟踪指数有清晰编制规则、连续 5 年以上稳定运行、成分股无大量"分红陷阱"（高分红但基本面恶化）
- 3 分：指数规则合理但成分股集中度过高（前 10 占比 > 50%），或有少数"分红陷阱"
- 1 分：成分股质量不稳定，分红可持续性存疑
- 0 分：跟踪的指数本身有问题

**REIT 适用**（底层物业/资产）：
- 5 分：核心地段（一线核心商圈、能源刚需地段、物流枢纽）、行业内 Top 级地位、不可替代性强
- 4 分：核心城市核心地段、有竞争力但不垄断
- 3 分：二线核心或一线非核心，运营稳定
- 2 分：三线城市或一线边缘，有运营压力
- 1 分：地段差或资产存在严重瑕疵
- 0 分：资产本身有重大问题（如大面积空置、资产纠纷）

### 维度 2：租约/合同稳定性（contract_stability）

> 现金流的"防御深度"

**ETF**：N/A（指数 ETF 没有租约概念，记 3 分跳过）

**REIT**：
- 5 分：长期合同（≥ 10 年）、租户极度分散（前 5 大 < 30%）、续租率 ≥ 95%、出租率 ≥ 98%
- 4 分：中期合同（5-10 年）、合理分散、续租率 ≥ 85%、出租率 ≥ 95%
- 3 分：短期合同（2-5 年）、租户略集中（前 5 大 30-50%）、续租率 70-85%
- 2 分：依赖少数大租户（前 3 大 > 50%）、出租率 90% 以下
- 1 分：高度依赖单一租户（前 1 大 > 50%）或出租率 80% 以下
- 0 分：主要租户面临违约/退租风险

### 维度 3：运营方实力（operator_strength）

> "这帮人靠不靠谱"

- 5 分：央企/国企背景头部基金（华夏/华润/中金/建信等）+ 该领域 5+ 年成熟运营记录 + 公开市场零负面
- 4 分：头部公募基金 + 该领域 3+ 年记录
- 3 分：中型基金 + 有一定记录，但非该领域专家
- 2 分：管理团队较新或换过手
- 1 分：有过运营事故/合规问题历史
- 0 分：管理人面临监管风险

### 维度 4：财务健康度（financial_health）

> "钱袋子撑不撑得住分红"

- 5 分：可分配金额覆盖率 ≥ 120%（每年实际能分的钱比承诺的多 20%+），NOI 连续 3 季增长，资产负债率 < 30%
- 4 分：覆盖率 100-120%，NOI 平稳，负债率 30-40%
- 3 分：覆盖率刚好 100%，NOI 略有波动，负债率 40-50%
- 2 分：覆盖率 80-100%（有时需要靠流动性应付分红），负债率 50-60%
- 1 分：覆盖率 < 80%，运营现金流明显不足
- 0 分：财务恶化，可能减分红或暂停分红

### 维度 5：政策/监管风险（regulatory_risk）

> "未来 5 年大概率会被政策影响吗？"

- 5 分：行业受国家政策明确鼓励（保租房、新能源、新基建）、税收稳定、扩募规则清晰
- 4 分：行业政策中性，没有明显风险
- 3 分：行业有一些政策不确定性，但短期内可控（如商业地产受房地产周期情绪影响）
- 2 分：面临行业政策收紧风险（如某些类型的园区/市政 REIT）
- 1 分：政策方向不利或税收待遇可能恶化
- 0 分：面临政策性强制清退/重组风险

### 维度 6：扩募/成长性（growth_potential）

> "未来 5 年这只 REIT 还能不能更大、更稳？"

- 5 分：原始权益人有大量优质储备资产（如华润万象城、印力旗下 30+ 商场）+ 已公告扩募方案 + 扩募会显著提升每份价值
- 4 分：储备资产充足，公开提及扩募意向
- 3 分：储备一般，未来 3 年可能扩募 1-2 次
- 2 分：储备有限，扩募空间小
- 1 分：底层资产单一且无扩募预期
- 0 分：原始权益人正在退出/缩减规模

## 综合得分计算

```ts
quality_score = sum of all 6 dimensions  // 0-30
quality_grade = 
  | "A+" if quality_score >= 26
  | "A"  if quality_score >= 22
  | "B+" if quality_score >= 18
  | "B"  if quality_score >= 14
  | "C"  if quality_score >= 10
  | "D"  if quality_score < 10
```

A+ 和 A 直接进入最终池；B+ 进入观察池；B 及以下淘汰。

## 给 DeepSeek 的执行规则

1. **必须引用证据**：每个维度评分必须配 1-3 句话的 reasoning，引用具体公开信息（年报/季报/公告/新闻），不能写"看起来不错"这种空话
2. **不知道就标 unknown**：如果某维度没有足够公开信息支撑评分，写 `score: null, reasoning: "信息不足，建议人工复核"`
3. **不要过度乐观**：宁可保守评 3 分，不要给陌生标的盲打 5 分
4. **专注公开信息**：不要编数据。如果年报说"出租率 95%"，就引用；不要凭空说"出租率应该不错"

## 输出 Schema

```ts
interface QualityAssessment {
  code: string;
  name: string;
  scores: {
    asset_quality: { score: number | null; reasoning: string; evidence: string[] };
    contract_stability: { score: number | null; reasoning: string; evidence: string[] };
    operator_strength: { score: number | null; reasoning: string; evidence: string[] };
    financial_health: { score: number | null; reasoning: string; evidence: string[] };
    regulatory_risk: { score: number | null; reasoning: string; evidence: string[] };
    growth_potential: { score: number | null; reasoning: string; evidence: string[] };
  };
  total_score: number;        // 0-30, null 维度按 missing 处理
  grade: 'A+' | 'A' | 'B+' | 'B' | 'C' | 'D' | 'INCOMPLETE';
  recommendation: 'include' | 'watch' | 'exclude';
  red_flags: string[];        // 重大风险列表
  upgrade_triggers: string[]; // 什么情况下评级会上升
}
```

## 限制与诚实声明

这套 framework 有以下局限，最终决策不能完全依赖它：

1. **LLM 可能产生幻觉**：尤其面对边缘标的，可能编造"看起来合理"的数据
2. **公开信息有滞后**：年报/季报披露后才能引用，最新动态需要人工补
3. **评分主观**：不同 LLM 跑同一只标的可能差 1-2 分
4. **不替代尽调**：投资决策前必须人工 review 红旗（red_flags）

→ Stage 5 由 Opus 把关，Stage 4 只是给 Stage 5 提供结构化输入。
