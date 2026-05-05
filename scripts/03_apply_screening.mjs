/**
 * Stage 3 · 量化筛选
 *
 * 输入：data/history.json
 * 输出：data/screened.json
 *
 * 规则严格按 methodology/02_screening_rules.md 执行。
 *
 * 不调 LLM。
 */

import { readJson, writeJson, timestamp } from './_lib/io.mjs';

const IN = 'data/history.json';
const OUT = 'data/screened.json';

// ============================================================
// 硬门槛规则
// ============================================================

// 当数据缺失时 SKIP（不淘汰），避免 false reject 优质标的
const SKIP_IF_NO_DATA = Symbol('skip-if-no-data');

const isManualListed = (t) =>
  String(t.metrics?.ttm_dividend_source ?? '').startsWith('manual');

// 注意：Tencent kline 限 1500 条 ≈ 2.7 年。所以 listing_years 的上限是 2.7。
// 真正上市超过 3 年的老标的（如 510880 19 年）我们靠 manual list 白名单豁免。
const ETF_HARD_GATES = {
  'ETF-H1': (t) =>
    isManualListed(t) ? SKIP_IF_NO_DATA : (t.listing_years ?? 0) >= 3,
  'ETF-H2': (t) => (t.aum ?? 0) >= 10e8,
  'ETF-H3': (t) =>
    isManualListed(t)
      ? SKIP_IF_NO_DATA
      : (t.metrics?.consecutive_dividend_years ?? 0) >= 2,
  'ETF-H4': () => SKIP_IF_NO_DATA,
  'ETF-H5': (t) => (t.metrics?.max_drawdown_pct ?? 100) <= 30,
  'ETF-H6': () => SKIP_IF_NO_DATA,
  // 同 REIT-H7：null 时 SKIP，避免 dividend API 不可用导致全量误杀
  'ETF-H7': (t) =>
    t.metrics?.current_yield_pct == null
      ? SKIP_IF_NO_DATA
      : t.metrics.current_yield_pct >= 3,
};

const REIT_HARD_GATES = {
  'REIT-H1': (t) =>
    isManualListed(t) ? SKIP_IF_NO_DATA : (t.listing_years ?? 0) >= 1.5,
  'REIT-H2': (t) => (t.aum ?? 0) >= 10e8,
  // H3/H7：dividend API 当前不可用。如 ttm_dividend 为 null（manual override 也没有）
  // → SKIP 不淘汰，让 Stage 4 LLM 主动评估；如有数据则正常判断
  'REIT-H3': (t) =>
    t.metrics?.ttm_dividend == null
      ? SKIP_IF_NO_DATA
      : t.metrics.ttm_dividend > 0,
  'REIT-H4': (t) => t.reit_subtype && t.reit_subtype !== 'other',
  'REIT-H5': () => SKIP_IF_NO_DATA,
  'REIT-H6': () => SKIP_IF_NO_DATA,
  'REIT-H7': (t) =>
    t.metrics?.current_yield_pct == null
      ? SKIP_IF_NO_DATA
      : t.metrics.current_yield_pct >= 3.5,
};

// ============================================================
// 软评分
// ============================================================

function scoreEtf(t) {
  const m = t.metrics ?? {};
  const yield_ = m.current_yield_pct ?? 0;
  const yield3y = m.three_year_avg_yield_pct ?? 0;
  const aum = t.aum ?? 0;
  const drawdown = m.max_drawdown_pct ?? 30;

  const breakdown = {
    yield: clamp(((yield_ - 3) / (8 - 3)) * 100),
    three_year_avg_yield: clamp(((yield3y - 3) / (8 - 3)) * 100),
    aum: clamp(Math.log10(aum / 10e8) * 25 + 50), // 50 分起，每个 10 倍 +25
    drawdown: clamp(((30 - drawdown) / (30 - 5)) * 100),
    historical_percentile: m.historical_percentile ?? 50,
  };
  const total =
    breakdown.yield * 0.35 +
    breakdown.three_year_avg_yield * 0.20 +
    breakdown.aum * 0.15 +
    breakdown.drawdown * 0.15 +
    breakdown.historical_percentile * 0.15;
  return { breakdown, total };
}

function scoreReit(t) {
  const m = t.metrics ?? {};
  const yield_ = m.current_yield_pct ?? 0;
  const aum = t.aum ?? 0;
  const ttmCount = m.ttm_dividend_count ?? 0;
  const historicalPercentile = m.historical_percentile;

  // REIT 不一定有 NAV 数据（universe 阶段没拿到）
  // 这里简化版：先不做溢价/折价评分
  const breakdown = {
    yield: clamp(((yield_ - 3.5) / (8 - 3.5)) * 100),
    historical_percentile: historicalPercentile ?? 50,
    aum: clamp(Math.log10(aum / 10e8) * 25 + 50),
    dividend_frequency:
      ttmCount >= 4 ? 100 : ttmCount === 3 ? 75 : ttmCount === 2 ? 50 : ttmCount === 1 ? 25 : 0,
    manager_rating: classifyManager(t.name),
  };
  const total =
    breakdown.yield * 0.30 +
    breakdown.historical_percentile * 0.25 +
    breakdown.aum * 0.15 +
    breakdown.dividend_frequency * 0.15 +
    breakdown.manager_rating * 0.15;
  return { breakdown, total };
}

function classifyManager(name) {
  // 央企/国企背景头部基金（华夏/华润/中金/建信/嘉实等）
  if (/华夏|华润|中金|建信|嘉实|中信建投|博时|易方达|南方|工银/.test(name))
    return 100;
  // 头部公募
  if (/招商|国泰|银华|大成|平安|广发/.test(name)) return 75;
  return 50;
}

function clamp(v) {
  return Math.max(0, Math.min(100, v));
}

// ============================================================
// 主流程
// ============================================================

function main() {
  const history = readJson(IN);
  const candidates = history.targets.filter((t) => t.status === 'ok');
  console.log(`[03] 处理 ${candidates.length} 只标的（其余为 Stage 2 失败）`);

  const results = candidates.map((t) => {
    const isReit = t.category === 'reit';
    const gates = isReit ? REIT_HARD_GATES : ETF_HARD_GATES;
    const passed = [];
    const failed = [];
    const skipped = [];
    for (const [id, fn] of Object.entries(gates)) {
      const r = fn(t);
      if (r === SKIP_IF_NO_DATA) skipped.push(id);
      else if (r) passed.push(id);
      else failed.push(id);
    }
    const all_passed = failed.length === 0;
    const { breakdown, total } = isReit ? scoreReit(t) : scoreEtf(t);

    return {
      code: t.code,
      name: t.name,
      market: t.market,
      category: t.category,
      reit_subtype: t.reit_subtype,
      listing_years: round(t.listing_years, 2),
      aum_yi: round(t.aum / 1e8, 2),
      ttm_dividend: round(t.metrics?.ttm_dividend, 4),
      current_yield_pct: round(t.metrics?.current_yield_pct, 2),
      three_year_avg_yield_pct: round(t.metrics?.three_year_avg_yield_pct, 2),
      max_drawdown_pct: round(t.metrics?.max_drawdown_pct, 1),
      historical_percentile: round(t.metrics?.historical_percentile, 1),
      hard_gates_passed: passed,
      hard_gates_failed: failed,
      hard_gates_skipped: skipped,
      score_breakdown: roundObj(breakdown, 1),
      total_score: round(total, 1),
      passed_to_stage4: all_passed,
    };
  });

  // 排序：按 total_score 降序
  results.sort((a, b) => b.total_score - a.total_score);

  // 计算类别内 rank
  const byCategory = {};
  for (const r of results) {
    const key = r.reit_subtype ?? r.category;
    if (!byCategory[key]) byCategory[key] = 0;
    if (r.passed_to_stage4) {
      byCategory[key]++;
      r.rank_in_category = byCategory[key];
    } else {
      r.rank_in_category = null;
    }
  }

  // 行业约束：每个 REIT 子类型最多 Top 5（原 Top 2，2026-05 扩池），
  // A 股红利 Top 5（市场仅 3 只全过），港股红利 Top 5（市场仅 1 只全过）
  for (const r of results) {
    if (!r.passed_to_stage4) continue;
    if (r.category === 'reit' && r.rank_in_category > 5) {
      r.passed_to_stage4 = false;
      r.exclude_reason = '类型内排名超出 Top 5';
    } else if (r.category === 'dividend_etf_a' && r.rank_in_category > 5) {
      r.passed_to_stage4 = false;
      r.exclude_reason = 'A 股红利 ETF 排名超出 Top 5';
    } else if (r.category === 'dividend_etf_hk' && r.rank_in_category > 5) {
      r.passed_to_stage4 = false;
      r.exclude_reason = '港股红利 ETF 排名超出 Top 5';
    }
  }

  const finalCount = results.filter((r) => r.passed_to_stage4).length;
  const passing = results.filter((r) => r.hard_gates_failed.length === 0);
  console.log(
    `[03] 硬门槛通过 ${passing.length} / 总 ${results.length}；最终进入 Stage 4: ${finalCount}`,
  );

  writeJson(OUT, {
    fetchedAt: timestamp(),
    summary: {
      total: results.length,
      hard_gates_passed: passing.length,
      passed_to_stage4: finalCount,
    },
    candidates: results,
  });
  console.log(`[03] ✅ 已写入 ${OUT}`);

  // 打印 Top 10
  console.log('\n[03] 进入 Stage 4 的 candidates:');
  console.log(
    'rank'.padEnd(5) +
      'code'.padEnd(8) +
      'name'.padEnd(30) +
      'score'.padEnd(8) +
      'yield'.padEnd(8) +
      'percentile',
  );
  console.log('-'.repeat(80));
  let i = 1;
  for (const r of results) {
    if (!r.passed_to_stage4) continue;
    console.log(
      String(i++).padEnd(5) +
        r.code.padEnd(8) +
        r.name.slice(0, 28).padEnd(30) +
        String(r.total_score).padEnd(8) +
        (r.current_yield_pct + '%').padEnd(8) +
        (r.historical_percentile != null
          ? r.historical_percentile + '%'
          : '?'),
    );
  }
}

function round(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return null;
  return Math.round(n * 10 ** digits) / 10 ** digits;
}

function roundObj(o, digits = 1) {
  const out = {};
  for (const [k, v] of Object.entries(o)) out[k] = round(v, digits);
  return out;
}

main();
