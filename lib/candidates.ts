import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { PRODUCTS } from './products';
import type { Market, ProductCategory } from './types';

/**
 * 候选池：在 seed_universe 里、Stage 3 量化筛选未通过、当前不在 dashboard 的标的。
 *
 * 主要落选原因：
 *   - 上市不足时长门槛
 *   - 规模不足 10 亿
 *   - dividend API 当前不可用 → REIT-H3/REIT-H7 被误判（重要：这是技术性 false positive）
 *   - 行业排名挤出（同子类型 Top 2 限额）
 *
 * 重新跑流水线时它们可能"成熟"通过 → 升级到 watch tier。
 */

export interface CandidateInfo {
  code: string;
  name: string;
  market: Market;
  category: ProductCategory;
  reitSubtype?: string | null;
  listingYears: number | null;
  aumYi: number | null;
  ttmDividend: number | null;
  currentYieldPct: number | null;
  maxDrawdownPct: number | null;
  totalScore: number | null;
  hardGatesFailed: string[];
  excludeReason?: string | null;
  /** 候选池分组（来自 categorizeCandidate）*/
  bucket?: CandidateBucket;
}

/** 候选池分组 — 按"为什么没进 monitored + 是否值得继续做工作"分类 */
export type CandidateBucket =
  | 'missing_ttm_etf' // 缺 TTM 分红的 ETF（补全后即可评估）
  | 'newly_listed' // 上市不足 1.5 年（等时间）
  | 'industry_squeeze' // 行业排名挤出（数据完整，调阈值即可）
  | 'low_yield' // 价格偏贵 yield 低（等回调）
  | 'small_aum' // 规模太小（结构性）
  | 'other'; // 其他

export const BUCKET_META: Record<
  CandidateBucket,
  { title: string; subtitle: string; priority: 'high' | 'medium' | 'low'; tone: string }
> = {
  missing_ttm_etf: {
    title: '📊 缺数据，补全可评估',
    subtitle: '缺 TTM 分红，需补全后才能进入 Stage 4 评估',
    priority: 'high',
    tone: 'amber',
  },
  industry_squeeze: {
    title: '📋 数据完整但被行业 Top 限制',
    subtitle: '同子类型已有 Top 2 占位 — 调阈值（如 Top 3）即可纳入',
    priority: 'high',
    tone: 'sky',
  },
  newly_listed: {
    title: '⏰ 新发不足 1.5 年',
    subtitle: '上市时间太短，等运营满 1.5 年自动达标',
    priority: 'medium',
    tone: 'slate',
  },
  low_yield: {
    title: '⏸ 当前价格偏贵',
    subtitle: '分派率 < 阈值，等价格回调',
    priority: 'low',
    tone: 'slate',
  },
  small_aum: {
    title: '📉 规模 < 10 亿',
    subtitle: '结构性问题（小盘流动性差），不建议跟踪',
    priority: 'low',
    tone: 'slate',
  },
  other: {
    title: '❓ 其他',
    subtitle: '查看 hardGatesFailed 字段了解具体原因',
    priority: 'low',
    tone: 'slate',
  },
};

function categorizeCandidate(c: CandidateInfo): CandidateBucket {
  const noTTM = c.ttmDividend == null || c.ttmDividend === 0;
  const isNew = c.listingYears != null && c.listingYears < 1.5;
  const yieldLow =
    c.currentYieldPct != null &&
    c.currentYieldPct < (c.category === 'reit' ? 3.5 : 3);
  const rankedOut = c.excludeReason?.includes('排名超出');
  const hardGatesH2 = c.hardGatesFailed.includes('REIT-H2') || c.hardGatesFailed.includes('ETF-H2');

  if (rankedOut) return 'industry_squeeze';
  if (isNew) return 'newly_listed';
  if (noTTM && c.category.startsWith('dividend_etf')) return 'missing_ttm_etf';
  if (yieldLow) return 'low_yield';
  if (hardGatesH2) return 'small_aum';
  return 'other';
}

/** Stage 3 硬门槛规则的人类可读描述 */
const REIT_GATE_REASONS: Record<string, string> = {
  'REIT-H1': '上市 < 1.5 年',
  'REIT-H2': '规模 < 10 亿',
  'REIT-H3': '近 12 月无分红记录',
  'REIT-H4': '子类型未分类',
  'REIT-H5': 'NOI 连续下跌',
  'REIT-H6': '解禁压力 > 30%',
  'REIT-H7': '当前分派率 < 3.5%',
};

const ETF_GATE_REASONS: Record<string, string> = {
  'ETF-H1': '上市 < 3 年',
  'ETF-H2': '规模 < 10 亿',
  'ETF-H3': '连续分红 < 2 年',
  'ETF-H4': '管理费 > 0.6%',
  'ETF-H5': '最大回撤 > 30%',
  'ETF-H6': '跟踪误差 > 1.5%',
  'ETF-H7': '当前股息率 < 3%',
};

export function loadCandidates(): CandidateInfo[] {
  const path = join(process.cwd(), 'data/screened.json');
  if (!existsSync(path)) return [];

  let raw: string;
  try {
    raw = readFileSync(path, 'utf8');
  } catch {
    return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }

  const data = parsed as { candidates?: Array<Record<string, unknown>> };
  if (!Array.isArray(data?.candidates)) return [];

  const monitored = new Set(PRODUCTS.map((p) => p.code));

  return data.candidates
    .filter((c) => typeof c.code === 'string' && !monitored.has(c.code as string))
    .map((c) => ({
      code: c.code as string,
      name: (c.name as string) ?? '',
      market: (c.market as Market) ?? 'sh',
      category: (c.category as ProductCategory) ?? 'reit',
      reitSubtype: (c.reit_subtype as string | null) ?? null,
      listingYears: numOrNull(c.listing_years),
      aumYi: numOrNull(c.aum_yi),
      ttmDividend: numOrNull(c.ttm_dividend),
      currentYieldPct: numOrNull(c.current_yield_pct),
      maxDrawdownPct: numOrNull(c.max_drawdown_pct),
      totalScore: numOrNull(c.total_score),
      hardGatesFailed: Array.isArray(c.hard_gates_failed)
        ? (c.hard_gates_failed as string[])
        : [],
      excludeReason: (c.exclude_reason as string | null) ?? null,
    }))
    .map((c) => ({ ...c, bucket: categorizeCandidate(c) }))
    .sort((a, b) => (b.totalScore ?? 0) - (a.totalScore ?? 0));
}

/** 按 bucket 分组返回 — 用于 dashboard 展示 */
export function groupCandidates(
  candidates: CandidateInfo[],
): Record<CandidateBucket, CandidateInfo[]> {
  const groups: Record<CandidateBucket, CandidateInfo[]> = {
    missing_ttm_etf: [],
    industry_squeeze: [],
    newly_listed: [],
    low_yield: [],
    small_aum: [],
    other: [],
  };
  for (const c of candidates) {
    if (c.bucket) groups[c.bucket].push(c);
  }
  return groups;
}

export function describeFailure(c: CandidateInfo): string[] {
  const out: string[] = [];
  if (c.excludeReason) out.push(c.excludeReason);
  const map = c.category === 'reit' ? REIT_GATE_REASONS : ETF_GATE_REASONS;
  for (const id of c.hardGatesFailed) {
    out.push(map[id] ?? id);
  }
  return out.length > 0 ? out : ['未知原因'];
}

function numOrNull(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  return v;
}
