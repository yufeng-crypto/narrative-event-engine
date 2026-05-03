/**
 * Smoke test：通过生产路径调 evaluateWithSearch 评估 1 只标的，确认
 * scripts/_lib/doubao_with_search.mjs 与 04_review_quality.mjs 接线正确。
 *
 * 用法：node --env-file=.env scripts/_scratch/smoke_doubao_searxng_pipeline.mjs
 */
import { evaluateWithSearch } from '../_lib/doubao_with_search.mjs';

const TARGET = {
  code: '508088',
  name: '国泰君安东久新经济REIT',
  category: 'reit',
  reit_subtype: 'industrial_park',
  ttm_dividend: 0.18,
  current_yield_pct: 5.2,
  total_score: 70,
};

console.log('Smoke test: evaluateWithSearch via production module');
console.log('Target:', TARGET.code, TARGET.name);
console.log('---');

const r = await evaluateWithSearch(TARGET, { verbose: true });
console.log('---');
console.log(`searches=${r.searchCount} iters=${r.iterations} cost=$${r.cost.toFixed(4)} (~¥${(r.cost*7.2).toFixed(2)})`);
console.log('parsed:', r.parsed ? 'OK' : `FAIL (${r.parseError})`);
if (r.parsed) {
  console.log('grade:', r.parsed.grade, 'total:', r.parsed.total_score);
  console.log('fact_anchor:', JSON.stringify(r.parsed.fact_anchor, null, 2));
  console.log('red_flags:', r.parsed.red_flags);
}
