export type Market = 'sh' | 'sz';
export type ProductCategory = 'dividend_etf_a' | 'dividend_etf_hk' | 'reit';
export type SignalLevel = 'hold' | 'watch' | 'buy_now';
/** 产品分级（来自 Stage 5 review）*/
export type Tier = 'core' | 'supporting' | 'watch';
/** 资产质量评级。A+/A 通常入核心或辅助；B+/B 入观察；C+/C/D 警示，建议剔除。*/
export type Grade = 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'D';

export interface ProductConfig {
  code: string;
  name: string;
  shortName: string;
  market: Market;
  category: ProductCategory;
  /** 产品分级（核心持仓/辅助持仓/监控池）*/
  tier: Tier;
  /** DeepSeek 评级（A+/A），来自 data/final_pool.json */
  grade: Grade;
  /** 综合得分 (0-30) from Stage 4 framework */
  qualityScore?: number;
  /** 关键风险提示（来自 Stage 4 评估）*/
  redFlags?: string[];
  /** tier 降级原因（如 180202 因到期归零降到 supporting）*/
  tierReason?: string;
  /** TTM dividend per share, in CNY. Manually maintained — see lib/products.ts */
  ttmDividend: number;
  /** ISO date the TTM dividend value was last verified */
  ttmDividendAsOf: string;
  /** Latest known fund net asset value (NAV), for premium calc. Optional. */
  navRefPrice?: number;
  navAsOf?: string;
  /** Realtime yield (%) at which signal escalates to 'watch' */
  watchYield: number;
  /** Realtime yield (%) at which signal escalates to 'buy_now' */
  buyYield: number;
  /** Optional absolute price ceiling for 'watch' (REITs use this) */
  watchPrice?: number;
  /** Optional absolute price ceiling for 'buy_now' */
  buyPrice?: number;
  notes?: string;
}

export interface Quote {
  code: string;
  name: string | null;
  price: number | null;
  prevClose: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  changePct: number | null;
  fetchedAt: string;
  source: 'eastmoney' | 'tencent' | 'mock' | 'error';
  error?: string;
}

export interface SignalResult {
  level: SignalLevel;
  /** Realtime TTM yield (%) computed from ttmDividend / current price */
  ttmYield: number | null;
  /** Premium (%) over NAV reference, if NAV is configured */
  premiumPct: number | null;
  /** Human-readable trigger reasons */
  triggers: string[];
}

export interface ProductView {
  config: ProductConfig;
  quote: Quote;
  signal: SignalResult;
  recommendation: Recommendation;
  dataStatus: DataStatus;
}

/**
 * 综合建议 — 合成 tier + grade + signal + redFlags 后的单一决策。
 * 这是给用户看的唯一"该怎么办"字段。
 */
export type RecommendationAction =
  | 'buy_now' // 立即建仓
  | 'small_test' // 小仓试水
  | 'watch_active' // 持仓观察
  | 'wait_pullback' // 等待回调
  | 'no_action' // 暂不建仓
  | 'avoid'; // 建议剔除

export interface Recommendation {
  action: RecommendationAction;
  label: string;
  /** UI 色调：success/warning/info/neutral/danger */
  tone: 'success' | 'warning' | 'info' | 'neutral' | 'danger';
  /** 一句话说明为什么 */
  reason: string;
}

/**
 * 数据完整度。dashboard 上明确告诉用户：决策建议是基于完整数据的，
 * 还是缺了什么所以不能给明确建议。
 */
export interface DataStatus {
  complete: boolean;
  /** 缺什么字段（如 'TTM 分红' / '实时报价' / '评估数据 90 天前'）*/
  missing: string[];
}
