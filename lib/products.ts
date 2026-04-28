import type { ProductConfig } from './types';

/**
 * 监控产品池 v0.3 — 来自完整 5 阶段流水线（2026-04-28）
 *
 * 流水线产物：data/final_pool.json
 *   Stage 1 (universe seed) → Stage 2 (history + manual TTM) →
 *   Stage 3 (量化筛选 8 通过) + Stage 4 (DeepSeek 6 维度评估 12 只) →
 *   Stage 5 (Opus tier 分级 + 风险显化)
 *
 * Tier 含义：
 *   - core (3 只 A+)：可优先建仓的核心持仓
 *   - supporting (5 只 A)：合格但有特殊处理（如 180202 当 11 年期债看）
 *   - watch (4 只 A 低)：留池但暂不建仓
 *
 * ttmDividend 仍是手动维护（dividend API 当前不可用，详见
 * methodology/manual_dividend_overrides.json）。每次有新分红公告
 * 回到这里更新。
 */
export const PRODUCTS: ProductConfig[] = [
  // ════════════════════════════════════════════════════════
  // 🥇 CORE — 3 只 A+ 级，扩募预期 + 央企背书 + 政策强支持
  // ════════════════════════════════════════════════════════
  {
    code: '180601',
    name: '华夏华润商业 REIT',
    shortName: '华润商业 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'core',
    grade: 'A+',
    qualityScore: 27,
    redFlags: [],
    ttmDividend: 0.3651,
    ttmDividendAsOf: '2026-02-28',
    navRefPrice: 6.53,
    navAsOf: '2025-12-31',
    watchYield: 4.3,
    buyYield: 4.8,
    watchPrice: 8.5,
    buyPrice: 8.0,
    notes: '青岛万象城。华润置地全国 80+ 万象城储备，扩募已尽调。当前 ~10 元溢价 50%，等回调到 8.5',
  },
  {
    code: '508077',
    name: '华夏基金华润有巢 REIT',
    shortName: '有巢保租房 REIT',
    market: 'sh',
    category: 'reit',
    tier: 'core',
    grade: 'A+',
    qualityScore: 27,
    redFlags: ['2025 年暂无新分红，关注下次公告'],
    ttmDividend: 0.13,
    ttmDividendAsOf: '2025-12-31',
    navRefPrice: 2.34,
    navAsOf: '2025-12-31',
    watchYield: 4.5,
    buyYield: 4.8,
    watchPrice: 2.7,
    buyPrice: 2.45,
    notes: '上海泗泾/奉贤东部经开区保租房。央企背景，政策最强支持，已公告扩募意向',
  },
  {
    code: '508028',
    name: '中信建投国家电投新能源 REIT',
    shortName: '国电投新能源 REIT',
    market: 'sh',
    category: 'reit',
    tier: 'core',
    grade: 'A+',
    qualityScore: 27,
    redFlags: ['海上风电来风波动影响短期 NOI'],
    ttmDividend: 0.30,
    ttmDividendAsOf: '2026-01-05',
    watchYield: 5.0,
    buyYield: 5.5,
    notes: '江苏盐城滨海北 H1/H2 海上风电。2026-03-30 战略配售解禁 24.7%，可能压价 → 加仓机会',
  },

  // ════════════════════════════════════════════════════════
  // 🥈 SUPPORTING — 5 只 A 级，可建仓但有特殊风险/处理
  // ════════════════════════════════════════════════════════
  {
    code: '513530',
    name: '港股通红利 ETF（华泰柏瑞）',
    shortName: '港股通红利',
    market: 'sh',
    category: 'dividend_etf_hk',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 22,
    redFlags: [],
    ttmDividend: 0.10,
    ttmDividendAsOf: '2026-03-17',
    watchYield: 5.2,
    buyYield: 5.8,
    notes: '港股通高股息指数 QDII，红利税优势（vs 港股通 20%）。每年最多 12 次分红',
  },
  {
    code: '510880',
    name: '上证红利 ETF（华泰柏瑞）',
    shortName: '上证红利',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 22,
    redFlags: ['成分股集中度较高（前十占 40%）'],
    ttmDividend: 0.142,
    ttmDividendAsOf: '2026-01-21',
    watchYield: 4.5,
    buyYield: 5.0,
    notes: 'A 股最老牌红利 ETF（2006 成立），上证红利指数 000015，规模 192 亿',
  },
  {
    code: '512890',
    name: '红利低波 ETF（华泰柏瑞）',
    shortName: '红利低波 50',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 22,
    redFlags: ['成分股集中度高（前十权重约 40%）'],
    ttmDividend: 0.060,
    ttmDividendAsOf: '2025-10-31',
    watchYield: 4.8,
    buyYield: 5.2,
    notes: '中证红利低波 H30269，规模 300+ 亿',
  },
  {
    code: '180202',
    name: '华夏越秀高速 REIT',
    shortName: '越秀高速 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 23,
    redFlags: [
      '⚠️ 特许经营权 2036 到期归零（剩 11 年）',
      '底层单一资产（汉孝高速 30km），集中度风险',
      '车流量增速放缓',
    ],
    tierReason: '应当 11 年期高息债处理，不是永续分红资产',
    ttmDividend: 0.38175,
    ttmDividendAsOf: '2026-01-31',
    navRefPrice: 6.08,
    navAsOf: '2025-06-30',
    watchYield: 4.8,
    buyYield: 5.5,
    notes: '湖北汉孝高速（武汉-孝感）。"越秀"是原始权益人非地名。2041 年特许权到期归零',
  },
  {
    code: '508098',
    name: '嘉实京东仓储基础设施 REIT',
    shortName: '京东物流',
    market: 'sh',
    category: 'reit',
    tier: 'supporting',
    grade: 'A',
    qualityScore: 24,
    redFlags: [
      '⚠️ 100% 关联方租户（京东自用）',
      '资产数量少（仅 3 个仓库）',
      '京东经营恶化即直接影响现金流',
    ],
    tierReason: '关联方风险高，单只持仓 ≤ 20w 限额',
    ttmDividend: 0.18,
    ttmDividendAsOf: '2026-01-22',
    navRefPrice: 3.47,
    navAsOf: '2025-12-31',
    watchYield: 5.0,
    buyYield: 5.5,
    notes: '京东重庆/武汉/廊坊仓库。出租率永远 100%（自用）但风险全押在京东',
  },

  // ════════════════════════════════════════════════════════
  // 🥉 WATCH — 4 只 A 低，留池但暂不建仓
  // ════════════════════════════════════════════════════════
  {
    code: '508058',
    name: '中金厦门安居 REIT',
    shortName: '厦门安居',
    market: 'sh',
    category: 'reit',
    tier: 'watch',
    grade: 'A',
    qualityScore: 25,
    redFlags: ['非厦门核心地段（集美区）', '可分配金额覆盖率 104%（偏低）'],
    tierReason: '非一线核心地段；不如 508077 有巢',
    ttmDividend: 0.12,
    ttmDividendAsOf: '2026-04-28',
    watchYield: 4.5,
    buyYield: 5.0,
    notes: '厦门集美区园博/珩琦公寓。出租率 99%+，但非岛内核心地段',
  },
  {
    code: '180602',
    name: '中金印力消费 REIT',
    shortName: '印力消费 REIT',
    market: 'sz',
    category: 'reit',
    tier: 'watch',
    grade: 'A',
    qualityScore: 24,
    redFlags: ['2024-04 才上市，分红刚起步（TTM 仅 0.0856）'],
    tierReason: '与 180601 同消费类，且分红刚起步',
    ttmDividend: 0.0856,
    ttmDividendAsOf: '2025-12-31',
    navRefPrice: 3.26,
    navAsOf: '2025-08-14',
    watchYield: 3.5,
    buyYield: 4.2,
    watchPrice: 3.8,
    buyPrice: 3.4,
    notes: '杭州西溪印象城（印力/万科）',
  },
  {
    code: '561580',
    name: '央企红利 ETF（华泰柏瑞）',
    shortName: '央企红利',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'watch',
    grade: 'A',
    qualityScore: 23,
    redFlags: ['上市仅 1.5 年，运营记录较短', '成分股集中度高'],
    tierReason: '运营记录太短，等观察 2-3 年',
    ttmDividend: 0.05,
    ttmDividendAsOf: '2026-04-28',
    watchYield: 4.8,
    buyYield: 5.3,
    notes: '中证央企红利指数 000825。央企+红利双主题',
  },
  {
    code: '515100',
    name: '红利低波 100 ETF（景顺长城）',
    shortName: '红利低波 100',
    market: 'sh',
    category: 'dividend_etf_a',
    tier: 'watch',
    grade: 'A',
    qualityScore: 22,
    redFlags: [],
    tierReason: '与 512890 同 A 股红利低波，二选一即可',
    ttmDividend: 0.064,
    ttmDividendAsOf: '2026-04-16',
    watchYield: 4.8,
    buyYield: 5.2,
    notes: '中证红利低波 100 (930955)，行业上限 20%，规模 64 亿（同类最大）',
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
