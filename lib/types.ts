export type Market = 'sh' | 'sz';
export type ProductCategory = 'dividend_etf_a' | 'dividend_etf_hk' | 'reit';
export type SignalLevel = 'hold' | 'watch' | 'buy_now';
/** 产品分级（来自 Stage 5 review）*/
export type Tier = 'core' | 'supporting' | 'watch';
/** DeepSeek 资产质量评级（A+/A 进入池，B/C/D 不入池）*/
export type Grade = 'A+' | 'A' | 'B+' | 'B' | 'C' | 'D';

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
}
