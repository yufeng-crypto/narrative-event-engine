/**
 * Stage 2 · 历史数据采集
 *
 * 输入：data/universe.json
 * 输出：data/history.json
 *
 * 对每只标的：
 * - 拉过去 5 年日线 → 计算最大回撤、年化波动率、3 年价格中位
 * - 拉历史分红 → 计算 TTM 分红、3 年股息率均值、连续分红年数
 *
 * 不调 LLM。纯 fetch + 计算。
 *
 * 注意：单 secid 拉 5 年日线一次返回，但 100 只标的 = 100 次串行调用，
 * 全程约 30-90 秒。出现错误的标的标记 status: 'error'，不中断。
 */

import { readFileSync } from 'node:fs';
import { fetchKline as fetchKlineMultiSource } from './_lib/quote_sources.mjs';
import { fetchDividendHistory } from './_lib/eastmoney.mjs';
import { readJson, writeJson, timestamp } from './_lib/io.mjs';

const IN = 'data/universe.json';
const OUT = 'data/history.json';
const OVERRIDES_PATH = 'methodology/manual_dividend_overrides.json';
const FROM_DATE = formatDate(daysAgo(20 * 365));

let MANUAL_OVERRIDES = {};
try {
  MANUAL_OVERRIDES = JSON.parse(readFileSync(OVERRIDES_PATH, 'utf8'))?.overrides ?? {};
  console.log(`[02] 加载 ${Object.keys(MANUAL_OVERRIDES).length} 条手动 TTM 分红 override`);
} catch (e) {
  console.log(`[02] 未找到 manual override 文件，纯靠 API 拉分红（当前不可用）`);
}

async function main() {
  const universe = readJson(IN);
  const targets = [...universe.dividend_etfs, ...universe.reits];
  console.log(`[02] 处理 ${targets.length} 只标的...`);

  const results = [];
  for (let i = 0; i < targets.length; i++) {
    const t = targets[i];
    process.stdout.write(`[02] (${i + 1}/${targets.length}) ${t.code} ${t.name}... `);
    try {
      const enriched = await processOne(t);
      results.push(enriched);
      console.log(
        `✓ TTM=${enriched.metrics.ttm_dividend?.toFixed(4) ?? '?'} ` +
          `yield=${enriched.metrics.current_yield_pct?.toFixed(2) ?? '?'}% ` +
          `mdd=${enriched.metrics.max_drawdown_pct?.toFixed(1) ?? '?'}%`,
      );
    } catch (e) {
      console.log(`✗ ${e.message}`);
      results.push({ ...t, status: 'error', error: e.message });
    }
    // 节流：不打爆东方财富
    await sleep(150);
  }

  writeJson(OUT, {
    fetchedAt: timestamp(),
    fromDate: FROM_DATE,
    targets: results,
  });
  console.log(`[02] ✅ 已写入 ${OUT}`);

  const errors = results.filter((r) => r.status === 'error');
  if (errors.length) {
    console.log(`[02] ⚠️ ${errors.length} 只失败（已留在 JSON 里供 debug）`);
  }
}

async function processOne(target) {
  const [klines, dividends] = await Promise.all([
    fetchKlineMultiSource(target.code, target.market, { beg: FROM_DATE.replace(/-/g, '') }),
    fetchDividendHistory(target.code).catch(() => []),
  ]);

  if (klines.length === 0) {
    throw new Error('no kline data');
  }

  const metrics = computeMetrics(klines, dividends);

  // 应用 manual override（如果有）
  const override = MANUAL_OVERRIDES[target.code];
  if (override?.ttm_dividend != null) {
    metrics.ttm_dividend = override.ttm_dividend;
    metrics.ttm_dividend_source = `manual:${override.as_of}`;
    if (metrics.current_price > 0) {
      metrics.current_yield_pct = (override.ttm_dividend / metrics.current_price) * 100;
    }
  } else if (metrics.ttm_dividend === 0 && dividends.length === 0) {
    // 既没 manual 也没 API 数据 → 标 missing
    metrics.ttm_dividend_source = 'missing';
    metrics.ttm_dividend = null;
    metrics.current_yield_pct = null;
  } else {
    metrics.ttm_dividend_source = 'api';
  }

  return {
    ...target,
    listing_date: klines[0]?.date ?? null,
    listing_years: klines[0] ? yearsSince(klines[0].date) : 0,
    n_klines: klines.length,
    n_dividends: dividends.length,
    metrics,
    status: 'ok',
  };
}

function computeMetrics(klines, dividends) {
  const closes = klines.map((k) => k.close);
  const currentPrice = closes[closes.length - 1];

  // 最大回撤
  let peak = closes[0];
  let mdd = 0;
  for (const c of closes) {
    if (c > peak) peak = c;
    const dd = (peak - c) / peak;
    if (dd > mdd) mdd = dd;
  }

  // 年化波动率（日收益率标准差 × √252）
  const returns = [];
  for (let i = 1; i < closes.length; i++) {
    returns.push(closes[i] / closes[i - 1] - 1);
  }
  const avg = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance =
    returns.reduce((s, r) => s + (r - avg) * (r - avg), 0) / returns.length;
  const annualVol = Math.sqrt(variance) * Math.sqrt(252);

  // TTM 分红：最近 12 个月内的分红总额
  const oneYearAgo = daysAgo(365);
  const ttmDivs = dividends.filter((d) => {
    if (!d.exDate) return false;
    return new Date(d.exDate) >= oneYearAgo;
  });
  const ttmDividend = ttmDivs.reduce((s, d) => s + (d.fhsl || 0), 0);

  // 3 年累计分红
  const threeYearsAgo = daysAgo(3 * 365);
  const threeYearDivs = dividends.filter((d) => {
    if (!d.exDate) return false;
    return new Date(d.exDate) >= threeYearsAgo;
  });
  const threeYearDividendTotal = threeYearDivs.reduce(
    (s, d) => s + (d.fhsl || 0),
    0,
  );

  // 3 年股息率均值（粗糙估算：3 年累计分红 / 3 年价格中位 / 3）
  const threeYearKlines = klines.filter(
    (k) => new Date(k.date) >= threeYearsAgo,
  );
  const threeYearMedianPrice =
    threeYearKlines.length > 0
      ? median(threeYearKlines.map((k) => k.close))
      : null;
  const threeYearAvgYieldPct =
    threeYearMedianPrice && threeYearMedianPrice > 0
      ? (threeYearDividendTotal / 3 / threeYearMedianPrice) * 100
      : null;

  // 当前 TTM 股息率
  const currentYieldPct =
    currentPrice > 0 ? (ttmDividend / currentPrice) * 100 : null;

  // 历史分位（当前股息率在过去 3 年股息率分布中的位置）
  // 简化实现：对每个交易日计算"过去 12 个月分红 / 当日价格"
  const historicalYields = [];
  for (const k of threeYearKlines) {
    const klineDate = new Date(k.date);
    const oneYearBefore = new Date(klineDate);
    oneYearBefore.setFullYear(oneYearBefore.getFullYear() - 1);
    const ttmAtThatDay = dividends
      .filter((d) => {
        if (!d.exDate) return false;
        const dDate = new Date(d.exDate);
        return dDate >= oneYearBefore && dDate <= klineDate;
      })
      .reduce((s, d) => s + (d.fhsl || 0), 0);
    if (k.close > 0 && ttmAtThatDay > 0) {
      historicalYields.push((ttmAtThatDay / k.close) * 100);
    }
  }
  let historicalPercentile = null;
  if (historicalYields.length > 30 && currentYieldPct != null) {
    const sorted = [...historicalYields].sort((a, b) => a - b);
    const below = sorted.filter((y) => y <= currentYieldPct).length;
    historicalPercentile = (below / sorted.length) * 100;
  }

  // 连续分红年数：从最近往前数，看哪一年开始没分红
  const yearsWithDiv = new Set();
  for (const d of dividends) {
    if (d.exDate) yearsWithDiv.add(d.exDate.slice(0, 4));
  }
  const currentYear = new Date().getFullYear();
  let consecutiveYears = 0;
  for (let y = currentYear; y >= currentYear - 10; y--) {
    if (yearsWithDiv.has(String(y))) consecutiveYears++;
    else break;
  }

  return {
    current_price: currentPrice,
    listing_date: klines[0]?.date ?? null,
    n_trading_days: klines.length,
    max_drawdown_pct: mdd * 100,
    annual_volatility_pct: annualVol * 100,
    ttm_dividend: ttmDividend,
    ttm_dividend_count: ttmDivs.length,
    current_yield_pct: currentYieldPct,
    three_year_dividend_total: threeYearDividendTotal,
    three_year_avg_yield_pct: threeYearAvgYieldPct,
    historical_percentile: historicalPercentile,
    consecutive_dividend_years: consecutiveYears,
  };
}

function median(arr) {
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d;
}

function yearsSince(dateStr) {
  return (Date.now() - new Date(dateStr).getTime()) / (365.25 * 24 * 3600 * 1000);
}

function formatDate(d) {
  return d.toISOString().slice(0, 10);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error('[02] ❌ Failed:', e);
  process.exit(1);
});
