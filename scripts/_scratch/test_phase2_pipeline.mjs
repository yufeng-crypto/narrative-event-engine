/**
 * Phase 2 - Step 2：完整管道 smoke。
 * 跑 508056（已知 Sonnet 找到"商誉减值 9889 万"）走 search+fetch 全流程，
 * 看 Doubao 能否自主选择 fetch + 抓到这个深层事实。
 *
 * 用法：node --env-file=.env scripts/_scratch/test_phase2_pipeline.mjs
 */

import { evaluateWithSearchAndFetch } from '../_lib/doubao_with_search_and_fetch.mjs';

const TARGET = {
  code: '508056',
  name: '中金普洛斯REIT',
  category: 'reit',
  reit_subtype: 'logistics',
  ttm_dividend: 0.18,
  current_yield_pct: 5.5,
  total_score: 75,
};

const TARGETS = ['商誉', '9889', '减值', '1.13亿'];

console.log('Phase 2 完整管道 smoke');
console.log('Target:', TARGET.code, TARGET.name);
console.log('期望找到关键事实: 2024 商誉减值 1.13亿 / 净利润 -9889 万');
console.log('---');

const r = await evaluateWithSearchAndFetch(TARGET, { verbose: true });
console.log('---');
console.log(
  `searches=${r.searchCount}/8 fetches=${r.fetchCount}/4 iters=${r.iterations} ` +
    `tokens=${r.usage.total_tokens} cost=$${r.cost.toFixed(4)} (~¥${(r.cost * 7.2).toFixed(2)})`,
);

if (!r.parsed) {
  console.log('parsed: FAIL', r.parseError);
  console.log('raw:', r.raw.slice(0, 500));
  process.exit(1);
}

console.log('parsed: OK');
console.log('grade:', r.parsed.grade, 'total:', r.parsed.total_score);
console.log('fact_anchor:', JSON.stringify(r.parsed.fact_anchor, null, 2));
console.log('red_flags:');
for (const rf of r.parsed.red_flags || []) console.log('  -', rf);
console.log('fetched_urls:', r.parsed.fetched_urls);

// 关键判断：是否抓到 Sonnet 的"商誉减值"发现
const flat = JSON.stringify(r.parsed);
const found = TARGETS.filter((kw) => flat.includes(kw));
console.log('---');
console.log(`🎯 Sonnet 关键发现命中：${found.length}/${TARGETS.length} → ${found.join(', ')}`);
console.log(
  found.length >= 2
    ? '✅ Phase 2 工作 — Doubao 通过 fetch 抓到了 Phase 1 漏掉的深层事实'
    : '❌ Phase 2 未达到目标 — 需要调 prompt 强制 fetch 或 fetch 没拉到关键页',
);
