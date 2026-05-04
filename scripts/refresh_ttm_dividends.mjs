/**
 * TTM 分红刷新 — fundf10 主路径 + Doubao+SearXNG 兜底。
 *
 * 设计：
 *   1. 主路径 fundf10.eastmoney.com/fhsp_<code>.html — 解析表格行（确定性，免 LLM 成本）
 *   2. 仅当 fundf10 无数据 / fetch 失败时降级到 Doubao + SearXNG（兜底）
 *
 * 用途：
 *   - 替换 manual_dividend_overrides.json 里 estimated_* 的不可靠数据
 *   - 刷过期数据
 *   - 能力 6 cron 月初自动跑
 *
 * 用法：
 *   # 刷所有 estimated_*
 *   FILTER=estimated node --env-file=.env scripts/refresh_ttm_dividends.mjs
 *
 *   # 刷指定 codes
 *   CODES=512890,515100,561580,513530 node --env-file=.env scripts/refresh_ttm_dividends.mjs
 *
 *   # 刷 >90 天没更新的
 *   STALE_DAYS=90 node --env-file=.env scripts/refresh_ttm_dividends.mjs
 *
 *   # 全部刷一遍（cron 月初用）
 *   ALL=1 node --env-file=.env scripts/refresh_ttm_dividends.mjs
 *
 *   # dry-run（不写文件）
 *   DRY_RUN=1 ... node --env-file=.env scripts/refresh_ttm_dividends.mjs
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { fetchFundf10Dividends } from './_lib/fundf10_dividend.mjs';
import { lookupTTMDividend } from './_lib/doubao_ttm_dividend.mjs';

const OVERRIDES_PATH = 'methodology/manual_dividend_overrides.json';
const PRODUCTS_PATH = 'lib/products.ts';

const CODES = process.env.CODES?.split(',').map((s) => s.trim()).filter(Boolean);
const FILTER = process.env.FILTER;
const STALE_DAYS = process.env.STALE_DAYS ? parseInt(process.env.STALE_DAYS) : null;
const ALL = process.env.ALL === '1';
const DRY_RUN = process.env.DRY_RUN === '1';

function extractProductsMap() {
  const txt = readFileSync(PRODUCTS_PATH, 'utf8');
  const map = new Map();
  const re = /code:\s*['"](\d+)['"][^}]*?name:\s*['"]([^'"]+)['"][^}]*?category:\s*['"]([^'"]+)['"]/gs;
  let m;
  while ((m = re.exec(txt))) {
    map.set(m[1], { code: m[1], name: m[2], category: m[3] });
  }
  return map;
}

function selectCodes(overrides) {
  const all = Object.keys(overrides);
  if (ALL) return all;
  if (CODES?.length) {
    const missing = CODES.filter((c) => !all.includes(c));
    if (missing.length) console.warn(`⚠️ 这些 code 不在 overrides 里：${missing.join(',')}`);
    return CODES.filter((c) => all.includes(c));
  }
  if (FILTER === 'estimated') {
    return all.filter((c) => /^(estimated_|rough_estimate)/.test(overrides[c].verified_by || ''));
  }
  if (STALE_DAYS) {
    const now = Date.now();
    return all.filter((c) => {
      const asOf = overrides[c].as_of;
      if (!asOf) return true;
      return Math.floor((now - new Date(asOf).getTime()) / 86400000) >= STALE_DAYS;
    });
  }
  // 默认：刷所有 estimated_*
  return all.filter((c) => /^(estimated_|rough_estimate)/.test(overrides[c].verified_by || ''));
}

async function refreshOne(code, productsMap) {
  const target = {
    code,
    name: productsMap.get(code)?.name || `代码 ${code}`,
    category: productsMap.get(code)?.category,
  };

  // 1. 尝试 fundf10 主路径
  const f10 = await fetchFundf10Dividends(code);
  if (f10.error) {
    return { code, source: 'fundf10_failed', error: f10.error, fallback_needed: true, target };
  }
  if (f10.ttm_dividend != null) {
    // fundf10 有结果（含 ttm=0 的明确"无分红"情况）
    return {
      code,
      source: 'fundf10',
      ttm_dividend: f10.ttm_dividend,
      dividends: f10.dividends,
      ttm_window: f10.ttm_window,
      explicit_no_dividend: f10.explicit_no_dividend,
      cost: 0,
      target,
    };
  }
  return { code, source: 'fundf10_empty', fallback_needed: true, target };
}

async function refreshOneWithDoubaoFallback(code, productsMap) {
  const primary = await refreshOne(code, productsMap);
  if (!primary.fallback_needed) return primary;

  // 2. fundf10 没数据 → 走 Doubao + SearXNG
  console.log(`    ↳ fundf10 无数据，降级 Doubao+SearXNG...`);
  const r = await lookupTTMDividend(primary.target);
  return {
    code,
    source: 'doubao_searxng',
    ttm_dividend: r.parsed?.ttm_dividend ?? null,
    dividends: r.parsed?.dividends ?? [],
    confidence: r.parsed?.confidence,
    cost: r.cost,
    target: primary.target,
    fundf10_status: primary.source, // fundf10_empty / fundf10_failed
  };
}

async function main() {
  const fileTxt = readFileSync(OVERRIDES_PATH, 'utf8');
  const file = JSON.parse(fileTxt);
  const overrides = file.overrides;
  const productsMap = extractProductsMap();

  const targets = selectCodes(overrides);
  if (targets.length === 0) {
    console.log('[ttm-refresh] ⚠️ 没有目标，退出');
    return;
  }

  console.log(`[ttm-refresh] 目标 ${targets.length} 只`);
  console.log(`[ttm-refresh] DRY_RUN=${DRY_RUN}`);
  console.log('---');

  let totalCost = 0;
  let totalChanged = 0;
  const summary = [];

  for (let i = 0; i < targets.length; i++) {
    const code = targets[i];
    const cur = overrides[code];
    const prod = productsMap.get(code);
    const name = prod?.name || `(未在 products.ts)`;
    process.stdout.write(`[${i + 1}/${targets.length}] ${code} ${name}... `);

    try {
      const r = await refreshOneWithDoubaoFallback(code, productsMap);
      totalCost += r.cost || 0;

      const oldTtm = cur.ttm_dividend;
      const newTtm = r.ttm_dividend;
      const delta = newTtm != null && oldTtm != null ? newTtm - oldTtm : null;
      const deltaPct = delta != null && oldTtm > 0 ? ((delta / oldTtm) * 100).toFixed(1) + '%' : '—';
      const changed = newTtm !== oldTtm;
      if (changed) totalChanged++;

      const note =
        r.source === 'fundf10' && r.explicit_no_dividend
          ? '⚠️ 显式无分红'
          : r.source === 'fundf10'
          ? `${r.dividends?.length || 0} 条 fundf10`
          : r.source === 'doubao_searxng'
          ? `Doubao ${r.confidence}`
          : `失败:${r.source}`;

      console.log(
        `${changed ? '✓ 改' : '= 同'} TTM ${oldTtm} → ${newTtm} (Δ ${deltaPct}) | ${note}`,
      );

      summary.push({ code, name, oldTtm, newTtm, source: r.source, note });

      if (!DRY_RUN && newTtm != null) {
        const verified =
          r.source === 'fundf10'
            ? r.explicit_no_dividend
              ? 'fundf10_no_dividend_history'
              : `fundf10_${r.dividends.length}dividends`
            : `doubao_searxng_${r.confidence ?? '?'}_${r.dividends?.length || 0}dividends`;

        overrides[code] = {
          ttm_dividend: newTtm,
          as_of: new Date().toISOString().slice(0, 10),
          verified_by: verified,
          ...(r.confidence && { confidence: r.confidence }),
          ...(r.explicit_no_dividend && { notes: '基金历史无分红记录（可能为累积型 ETF）' }),
        };
      }
    } catch (e) {
      console.log(`✗ ${e.message}`);
      summary.push({ code, name, error: e.message });
    }
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log('---');
  console.log(`[ttm-refresh] 总成本: $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(2)})`);
  console.log(`[ttm-refresh] 改动: ${totalChanged}/${targets.length}`);

  if (DRY_RUN) {
    console.log('[ttm-refresh] DRY_RUN=1，不写文件');
    return;
  }

  file.lastUpdated = new Date().toISOString().slice(0, 10);
  if (!file.changelog) file.changelog = [];
  file.changelog.unshift(
    `${file.lastUpdated} TTM refresh: ${totalChanged} 只更新 (fundf10 主 + Doubao 兜底)`,
  );
  writeFileSync(OVERRIDES_PATH, JSON.stringify(file, null, 2) + '\n', 'utf8');
  console.log(`[ttm-refresh] ✅ 已写入 ${OVERRIDES_PATH}`);
}

main().catch((e) => {
  console.error('[ttm-refresh] ❌ Failed:', e);
  process.exit(1);
});
