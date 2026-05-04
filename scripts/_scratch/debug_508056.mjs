/**
 * 单只 debug：508056 Stage B 反复 timeout，查根因。
 *
 * 假设排查：
 * 1. Stage A 输出是否过短/过长？
 * 2. Stage B 单独跑能否成功？
 * 3. 是不是 Doubao 对 "中金普洛斯" 这类标的的请求特别慢？
 */
import { readJson } from '../_lib/io.mjs';
import { evaluateWithSearchAndFetch } from '../_lib/doubao_with_search_and_fetch.mjs';
import { callDoubaoWithMessages, estimateDoubaoCost } from '../_lib/doubao.mjs';

const phase1 = readJson('data/quality_scores_doubao_searxng.json');
const phase1Map = new Map();
for (const a of phase1.assessments || []) {
  if (a.status === 'ok' && a.fact_anchor) phase1Map.set(a.code, a.fact_anchor);
}

const TARGET = {
  code: '508056',
  name: '中金普洛斯REIT',
  category: 'reit',
  reit_subtype: 'logistics',
  ttm_dividend: 0.18,
  current_yield_pct: 5.5,
  total_score: 75,
};

console.log('Debug 508056 Stage B timeout');
console.log('Phase 1 seed:', phase1Map.get('508056')?.underlying_asset);
console.log('---');

const r = await evaluateWithSearchAndFetch(TARGET, {
  knownFactAnchor: phase1Map.get(TARGET.code),
  verbose: true,
});

console.log('---');
console.log('Stage A length:', r.raw?.length);
console.log('Stage A tail (200 chars):');
console.log((r.raw || '').slice(-200));
console.log('---');
console.log('Stage B raw length:', r.stageBRaw?.length);
console.log('parseError:', r.parseError);
console.log('parsed?', !!r.parsed);
if (r.parsed) {
  console.log('grade:', r.parsed.grade, 'total:', r.parsed.total_score);
}
console.log(`s=${r.searchCount} f=${r.fetchCount} cost=$${r.cost.toFixed(4)}`);
