/**
 * Phase 2 v2 smoke：测两阶段输出 + Phase 1 seed。
 * 用 508005（v1 退化成 unknown）+ 180501（v1 退化）验证 seed 解决退化问题。
 */
import { readJson } from '../_lib/io.mjs';
import { evaluateWithSearchAndFetch } from '../_lib/doubao_with_search_and_fetch.mjs';

const phase1 = readJson('data/quality_scores_doubao_searxng.json');
const phase1Map = new Map();
for (const a of phase1.assessments || []) {
  if (a.status === 'ok' && a.fact_anchor) phase1Map.set(a.code, a.fact_anchor);
}

const targets = [
  { code: '508005', name: '华夏首创奥莱REIT', category: 'reit', reit_subtype: 'consumer', ttm_dividend: 0.20, current_yield_pct: 5.0, total_score: 65 },
  { code: '180501', name: '红土创新深圳安居REIT', category: 'reit', reit_subtype: 'rental_housing', ttm_dividend: 0.15, current_yield_pct: 4.8, total_score: 70 },
];

for (const t of targets) {
  console.log('\n===', t.code, t.name, '===');
  const seed = phase1Map.get(t.code);
  console.log('seed:', seed?.underlying_asset?.slice(0, 50), '...');
  const r = await evaluateWithSearchAndFetch(t, { knownFactAnchor: seed, verbose: true });
  console.log(`s=${r.searchCount} f=${r.fetchCount} cost=$${r.cost.toFixed(4)} parsed=${!!r.parsed}`);
  if (r.parsed) {
    console.log('grade:', r.parsed.grade, 'total:', r.parsed.total_score);
    console.log('fact_anchor.confidence:', r.parsed.fact_anchor?.verification_confidence);
    console.log('fallback:', !!r.parsed._fact_anchor_fallback);
    console.log('red_flags:', r.parsed.red_flags?.length);
    for (const rf of r.parsed.red_flags || []) console.log('  -', rf);
  } else {
    console.log('parseError:', r.parseError);
    console.log('stageA tail:', r.raw.slice(-300));
    console.log('stageB tail:', r.stageBRaw?.slice(-300));
  }
}
