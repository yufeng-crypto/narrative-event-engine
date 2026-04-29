import type { ProductConfig } from './types';

/**
 * 监控产品池 v0.5 — Sonnet 全 12 只评估完成（2026-04-28）
 *
 * 流水线：
 *   Stage 1 (universe seed) → Stage 2 (history + manual TTM) →
 *   Stage 3 (量化筛选 8 通过) → Stage 4 (Sonnet 6 维度评估，全 12 只) →
 *   Stage 5 v3 (Opus 把关 + 风险显化)
 *
 * v0.4 → v0.5 调整（基于 Sonnet 补跑 4 只评估）：
 *   - 561580 央企红利：watch → CORE（Sonnet 25 分，政策最强支持，规模 1.5 年涨 2.4 倍）
 *   - 508058 厦门安居：watch → SUPPORTING（覆盖率 102% 健康，岛内扩募已受理）
 *   - 508028 国电投新能源：core → SUPPORTING（Sonnet 23 分，可分配 -14%，依赖保理）
 *   - 180602 印力消费：watch（保持，万科系流动性危机风险传导）
 *
 * Tier 含义：
 *   - core (3 只)：A 24-25 分，政策强支持 + 扩募预期，可优先建仓
 *   - supporting (3 只)：A 22-24 分，合格但有特殊处理 / 等条件
 *   - watch (6 只)：A 22 / B+ 18-20 分，留池但暂不建仓
 *
 * ttmDividend 仍手动维护（dividend API 当前不可用）。
 * 每次新分红公告 → 回到 manual_dividend_overrides.json 更新。
 */
export const PRODUCTS: ProductConfig[] = [
  // ════════════════════════════════════════════════════════
  // 🥇 CORE — 3 只，可优先建仓的核心持仓
  // ════════════════════════════════════════════════════════
  {
    code: '180601',
    name: '华夏华润商业 REIT',
    shortName: '华润商业 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'core',
    grade: 'A',
    qualityScore: 24,
    redFlags: [
      'WALE 仅 1.99 年（短租约结构）',
      '底层资产单一（青岛万象城），扩募完成前集中度高',
      '当前价格使分派率仅 3.64%，溢价偏高',
    ],
    tierReason: '扩募已实质推进（昆山 + 萧山/沈阳/淄博四项目受理），等价格回调到 8.5 元',
    ttmDividend: 0.3651,
    ttmDividendAsOf: '2026-02-28',
    navRefPrice: 6.53,
    navAsOf: '2025-12-31',
    watchYield: 4.3,
    buyYield: 4.8,
    watchPrice: 8.5,
    buyPrice: 8.0,
    notes: '青岛万象城。出租率 99%+ 客流 +10.9%。华润 92 个万象城在营 / 规划 127 个，扩募节奏全市场最快',
  },
  {
    code: '512890',
    name: '红利低波 ETF（华泰柏瑞）',
    shortName: '红利低波 50',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'core',
    grade: 'A',
    qualityScore: 25,
    redFlags: [
      '行业高度集中：银行 37.5% + 煤炭 15.3%（前两合计 52%）',
      'ETF 分红需累计报酬超指数 1%，分红确定性低于 REIT',
      '同赛道 16 只 ETF 竞争',
    ],
    tierReason: 'A 股红利 ETF 最优（Sonnet 25 分），跟踪 H30269 含分红正增长筛选，规模 307 亿',
    ttmDividend: 0.060,
    ttmDividendAsOf: '2025-10-31',
    watchYield: 4.8,
    buyYield: 5.2,
    notes: '中证红利低波 H30269（50 只样本，前 10 集中 27%）。柳军 2018-12 起任职，6 年全部正收益。新国九条 + 险资入市政策强利好',
  },
  {
    code: '561580',
    name: '央企红利 ETF（华泰柏瑞）',
    shortName: '央企红利',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'core',
    grade: 'A',
    qualityScore: 25,
    redFlags: [
      '金融（银行）板块 33.5% + 前 10 集中 60%+',
      '费率 0.60% 高于同类红利低波 100（0.15%）',
      '运营仅 3 年（2023-05 上市），未经历完整周期',
      '富国 159332 同跟踪 000825 形成竞争',
    ],
    tierReason: '政策最强支持赛道（国资委市值管理 + 央企分红考核 + 新国九条三重利好），规模 1.5 年涨 2.4 倍',
    ttmDividend: 0.05,
    ttmDividendAsOf: '2026-04-28',
    watchYield: 4.5,
    buyYield: 5.0,
    notes: '中证央企红利指数 000825（50 只央企含中国神华/中国移动/建行）。规模 6.4 亿（2024 末）→ 15.35 亿（2026-03）',
  },

  // ════════════════════════════════════════════════════════
  // 🥈 SUPPORTING — 3 只，合格但需 caveat
  // ════════════════════════════════════════════════════════
  {
    code: '508077',
    name: '华夏基金华润有巢 REIT',
    shortName: '有巢保租房 REIT',
    market: 'sh',
    category: 'reit',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 22,
    redFlags: [
      '⚠️ 2024 实际分配 6541 万 > 可分配 4904 万（超额 33%），消耗净资产',
      '基金份额净值自成立累计 -7.4%（2.4310 → 2.2508）',
      '公寓 WALE 仅 0.52 年',
      '商业部分出租率仅 63%（同比 -8.55pct）',
      '扩募后预测分派率仅 3.3%（低于当前 4.75%），存在摊薄压力',
    ],
    tierReason: '保租房政策 5 分但超额分配是隐藏问题，等可分配覆盖率回到 100%+ 再加仓',
    ttmDividend: 0.13,
    ttmDividendAsOf: '2025-12-31',
    navRefPrice: 2.34,
    navAsOf: '2025-12-31',
    watchYield: 4.5,
    buyYield: 4.8,
    watchPrice: 2.7,
    buyPrice: 2.45,
    notes: '上海松江有巢泗泾 + 东部经开区保租房。央企华润背景。马桥项目扩募 2024-11 受理',
  },
  {
    code: '508058',
    name: '中金厦门安居 REIT',
    shortName: '厦门安居',
    market: 'sh',
    category: 'reit',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 24,
    redFlags: [
      '集美区岛外，租金单价（约 34 元/sqm/月）和增速低于厦门岛内',
      '扩募拟引入公租房（仁和公寓），政策管控更严，可能拉低组合租金',
      '基金净资产 2024 年 -2.52%（折旧摊销，REITs 通性）',
    ],
    tierReason: '✅ 关键：覆盖率 102% 健康（不像 508077 超额分配）。岛内扩募已 2025-04 受理，地段升级',
    ttmDividend: 0.12,
    ttmDividendAsOf: '2026-04-28',
    navRefPrice: null as unknown as undefined,
    watchYield: 4.5,
    buyYield: 5.0,
    notes: '厦门集美区园博/珩琦公寓（4665 套）。出租率 99.7%+ 个人租户 93.86%。拟扩募林边（思明）+ 仁和（湖里）→ 岛内核心',
  },
  {
    code: '510880',
    name: '上证红利 ETF（华泰柏瑞）',
    shortName: '上证红利',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 23,
    redFlags: [
      '⚠️ 费率 0.60% 偏高（行业头部已降至 0.20%），长期持有成本劣势',
      '选股仅限上交所（不含深市/北交所）',
      '单因子（仅股息率），周期股分红可持续性存疑',
    ],
    tierReason: '老牌但费率高，等降费后再加；当前 19 年记录是真的护城河',
    ttmDividend: 0.142,
    ttmDividendAsOf: '2026-01-21',
    watchYield: 4.5,
    buyYield: 5.0,
    notes: 'A 股最老牌红利 ETF（2006 成立）。上证红利指数 000015，规模 192 亿。连续 15 年分红，6 年正收益累计利润 76 亿',
  },

  // ════════════════════════════════════════════════════════
  // 🥉 WATCH — 6 只，留池但暂不建仓
  // ════════════════════════════════════════════════════════
  {
    code: '508028',
    name: '中信建投国家电投新能源 REIT',
    shortName: '国电投新能源',
    market: 'sh',
    category: 'reit',
    tier: 'watch',
    grade: 'A',
    qualityScore: 23,
    redFlags: [
      '⚠️ 2025 可分配 -14.13%（66907 vs 上年 77917 万）',
      '⚠️ Q3 单季可分配 -979 万（电网停电 14 天 + 风速偏低）',
      '⚠️ 国补保理融资 38.18 亿，依赖保理融资完成分配',
      '⚠️ 2026-03-30 战略配售解禁 24.7%（已发生），流通盘扩大',
      '电力市场化交易敞口扩大（已 8.02%）',
      '送出线路单一，电网停电直接影响发电量',
    ],
    tierReason: 'Sonnet 23 分，从 core 降级。等可分配恢复 + 滨海~鹤栖 500kV 投运',
    ttmDividend: 0.30,
    ttmDividendAsOf: '2026-01-05',
    watchYield: 5.0,
    buyYield: 5.5,
    notes: '江苏盐城滨海北 H1/H2 海上风电（500MW）。央企国家电投。海风 50% 增值税即征即退延续到 2027-12',
  },
  {
    code: '180602',
    name: '中金印力消费 REIT',
    shortName: '印力消费 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'watch',
    grade: 'A',
    qualityScore: 22,
    redFlags: [
      '⚠️ 万科系流动性危机：万科 2025Q3 现金短债比 0.43，运营资源 + 品牌稳定性受联动',
      '底层单一资产（西溪印象城），高度依赖杭州城西',
      'WALE 仅 2.53 年（短租）',
      '管理费 4052 万 > 净利润 1929 万，费用结构偏高',
      '2025-11 万科展期后 REIT 单日跌 2.7%',
    ],
    tierReason: '资产本身健康（覆盖率 102-104%），但万科系风险传导是结构性问题',
    ttmDividend: 0.0856,
    ttmDividendAsOf: '2025-12-31',
    navRefPrice: 3.26,
    navAsOf: '2025-08-14',
    watchYield: 3.5,
    buyYield: 4.2,
    watchPrice: 3.8,
    buyPrice: 3.4,
    notes: '杭州西溪印象城（印力/万科）。出租率 99%+ 客流 +10.72%。等万科流动性危机化解',
  },
  {
    code: '513530',
    name: '港股通红利 ETF（华泰柏瑞）',
    shortName: '港股通红利',
    market: 'sh',
    category: 'dividend_etf_hk',
    tier: 'watch',
    grade: 'B+',
    qualityScore: 20,
    redFlags: [
      '⚠️ QDII 额度紧张：21.63% 资产已转港股通渠道，红利税升至 20%',
      '30 只样本前 4 行业集中 68%（银行+交运+煤炭+石油）',
      '最大回撤 18.4% + 汇率波动',
      '2026-04 份额从 22.52 亿降至 19.60 亿（-13%）',
    ],
    tierReason: 'QDII 税收优势已部分稀释；等额度恢复或港股估值修复',
    ttmDividend: 0.10,
    ttmDividendAsOf: '2026-03-17',
    watchYield: 5.2,
    buyYield: 5.8,
    notes: '中证港股通高股息（930915）QDII 模式。理论税收优势 vs 港股通 20%，但额度紧张已实质打折',
  },
  {
    code: '180202',
    name: '华夏越秀高速 REIT',
    shortName: '越秀高速 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'watch',
    grade: 'B+',
    qualityScore: 18,
    redFlags: [
      '⚠️ 2024 可分配金额同比 -22%，2025Q2 通行费同比 -6.86%',
      '⚠️ 折旧摊销 2025Q2 同比 +23.26%（成本结构性上升）',
      '⚠️ 合并资产负债率 86.6%（含 ABS 内部债）',
      '⚠️ 特许经营权剩余约 10 年（2036-12 到期），净值趋零',
      '京港澳改扩建持续分流，竞争路网趋于成熟',
      '无任何扩募进展，单一资产 + 资产老化',
    ],
    tierReason: '7% 分派率是衰退预期 price-in 的结果。当 11 年期到期归零债看，单只 ≤ 10w',
    ttmDividend: 0.38175,
    ttmDividendAsOf: '2026-01-31',
    navRefPrice: 6.08,
    navAsOf: '2025-06-30',
    watchYield: 4.8,
    buyYield: 5.5,
    notes: '湖北汉孝高速（武汉-孝感 33km）。"越秀"是原始权益人非地名。Sonnet 18 分严格降级',
  },
  {
    code: '508098',
    name: '嘉实京东仓储基础设施 REIT',
    shortName: '京东物流',
    market: 'sh',
    category: 'reit',
    tier: 'watch',
    grade: 'B+',
    qualityScore: 18,
    redFlags: [
      '⚠️ 100% 京东系关联方租户，单一企业生态圈风险',
      '⚠️ 廊坊 2026-05 起续租降租 30%（39.39 → 27.68 元/sqm/月）',
      '⚠️ 重庆 2025 年起降租，武汉 2024 年起降租 13%',
      '⚠️ NOI 连续下行：2025 收入 -1.77% / 现金流 -10.05% / Q1 可分配 -14.44%',
      '廊坊周边市场租金已较 2020 年腰斩',
      '关联交易定价独立性存疑',
    ],
    tierReason: '所有 3 处资产都在降租；等续租企稳或资产分散后再考虑',
    ttmDividend: 0.18,
    ttmDividendAsOf: '2026-01-22',
    navRefPrice: 3.47,
    navAsOf: '2025-12-31',
    watchYield: 5.0,
    buyYield: 5.5,
    notes: '京东重庆/武汉/廊坊 3 处仓库（35.1 万 sqm）。出租率 100% 但租金连续下调',
  },
  {
    code: '515100',
    name: '红利低波 100 ETF（景顺长城）',
    shortName: '红利低波 100',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'watch',
    grade: 'B+',
    qualityScore: 20,
    redFlags: [
      '⚠️ 2025 年分红 0.1053 元 vs 2023 年 0.4370 元，下降 76%',
      '指数不含 ROE 筛选（vs 512890 H30269 含分红正增长筛选）',
      '钢铁（9%）+ 化工（8%）周期股占比高',
      '现任经理 2023-11 才接管，记录仅 2.5 年',
    ],
    tierReason: '同 A 股红利低波，512890 已升 core；这只让位',
    ttmDividend: 0.064,
    ttmDividendAsOf: '2026-04-16',
    watchYield: 4.8,
    buyYield: 5.2,
    notes: '中证红利低波 100（930955）。景顺长城管理。规模 62 亿同类第一但 Sonnet 评分降到 B+',
  },
];

export function findProduct(code: string): ProductConfig | undefined {
  return PRODUCTS.find((p) => p.code === code);
}

/** Tier 排序权重，用于 dashboard 排序 */
export const TIER_ORDER: Record<string, number> = {
  core: 0,
  supporting: 1,
  watch: 2,
};
