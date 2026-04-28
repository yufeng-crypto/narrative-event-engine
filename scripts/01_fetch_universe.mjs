/**
 * Stage 1 · 全市场宇宙采集（seed-based）
 *
 * 输入：methodology/seed_universe.json
 * 输出：data/universe.json
 *
 * 策略变更（2026-04-28）：
 *   不再尝试动态扫描全市场（东方财富没有公开的 REITs 全列表 JSON 接口，
 *   且代码段扫描会触发 rate limit）。改用 seed list + 实时验证存在性。
 *   详见 methodology/01_universe_strategy.md
 *
 * 流程：
 *   - 读 seed_universe.json
 *   - 跳过 status=delisted
 *   - 对每只 status=active/pending：调单只 quote API 验证存在 + 抓元数据
 *   - 失败的标记 status='invalid'，留在结果里供 debug
 *
 * 不调 LLM。低 API 压力（约 50 次调用，350ms 节流 → 总耗时 < 1 分钟）。
 */

import { readFileSync } from 'node:fs';
import { writeJson, timestamp } from './_lib/io.mjs';
import { fetchQuote } from './_lib/quote_sources.mjs';

const SEED_PATH = 'methodology/seed_universe.json';
const OUT = 'data/universe.json';
const THROTTLE_MS = 250;

async function main() {
  const seed = JSON.parse(readFileSync(SEED_PATH, 'utf8'));
  const allSeeds = [
    ...(seed.dividend_etfs_a || []).map((s) => ({ ...s, category: 'dividend_etf_a' })),
    ...(seed.dividend_etfs_hk || []).map((s) => ({ ...s, category: 'dividend_etf_hk' })),
    ...(seed.reits || []).map((s) => ({ ...s, category: 'reit' })),
  ];
  const active = allSeeds.filter((s) => s.status !== 'delisted');
  console.log(`[01] Seed list: 总 ${allSeeds.length}, 有效 ${active.length}`);

  const results = [];
  let validated = 0;
  let invalid = 0;

  for (let i = 0; i < active.length; i++) {
    const s = active[i];
    process.stdout.write(`[01] (${i + 1}/${active.length}) ${s.code} ${s.name}... `);
    try {
      const q = await fetchQuote(s.code, s.market);
      results.push({
        code: s.code,
        name: q.name || s.name,
        market: s.market,
        category: s.category,
        reit_subtype: s.reit_subtype || null,
        current_price: q.price,
        prev_close: q.prevClose,
        change_pct: q.changePct,
        aum: q.aum ?? null,
        seed_source: s.notes || null,
        validation: {
          status: 'ok',
          name_match: q.name === s.name,
          name_in_data: q.name,
          source: q.source,
        },
      });
      validated++;
      console.log(`✓ ${q.source} 价 ${q.price} 名 ${q.name}`);
    } catch (e) {
      results.push({
        code: s.code,
        name: s.name,
        market: s.market,
        category: s.category,
        reit_subtype: s.reit_subtype || null,
        current_price: null,
        validation: { status: 'invalid', error: e.message },
      });
      invalid++;
      console.log(`✗ ${e.message}`);
    }
    await sleep(THROTTLE_MS);
  }

  const dividend_etfs = results.filter(
    (r) => r.category === 'dividend_etf_a' || r.category === 'dividend_etf_hk',
  );
  const reits = results.filter((r) => r.category === 'reit');

  writeJson(OUT, {
    fetchedAt: timestamp(),
    counts: {
      seed_total: active.length,
      validated,
      invalid,
      dividend_etfs: dividend_etfs.length,
      reits: reits.length,
    },
    dividend_etfs,
    reits,
  });

  console.log(
    `[01] ✅ 已写入 ${OUT}：validated ${validated}（红利 ETF ${dividend_etfs.length}, REITs ${reits.length}），invalid ${invalid}`,
  );
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error('[01] ❌ Failed:', e);
  process.exit(1);
});
