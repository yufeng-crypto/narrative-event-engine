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
    .sort((a, b) => (b.totalScore ?? 0) - (a.totalScore ?? 0));
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
