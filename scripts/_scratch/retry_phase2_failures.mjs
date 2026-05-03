/**
 * 重跑 Phase 2 第一轮里失败的 7 只标的，把结果合并进
 * data/quality_scores_doubao_searxng_fetch.json。
 *
 * 失败原因：
 *   - 3 只 JSON 输出截断（max_tokens=4096 不够）
 *   - 4 只 "fetch failed"（晚期网络/quota 抖动，已加 3 次重试）
 *
 * 用法：node --env-file=.env scripts/_scratch/retry_phase2_failures.mjs
 */

import { readJson, writeJson, timestamp } from '../_lib/io.mjs';
import { evaluateWithSearchAndFetch } from '../_lib/doubao_with_search_and_fetch.mjs';

const SCREENED = readJson('data/screened.json');
const EXISTING = readJson('data/quality_scores_doubao_searxng_fetch.json');
const failed = EXISTING.assessments.filter((a) => a.status !== 'ok').map((a) => a.code);
const candidates = SCREENED.candidates.filter((c) => failed.includes(c.code));

console.log(`重跑失败 ${failed.length} 只:`, failed.join(','));

const newResults = [];
let totalCost = 0;

for (let i = 0; i < candidates.length; i++) {
  const c = candidates[i];
  process.stdout.write(`(${i + 1}/${candidates.length}) ${c.code} ${c.name}... `);
  try {
    const r = await evaluateWithSearchAndFetch(c, {
      maxIterations: 14,
      maxSearches: 8,
      maxFetches: 4,
      verbose: false,
    });
    totalCost += r.cost;
    if (!r.parsed) {
      newResults.push({
        code: c.code,
        name: c.name,
        status: 'error',
        error: `JSON parse failed: ${r.parseError ?? 'unknown'}`,
        raw: (r.raw || '').slice(0, 3000),
        searchCount: r.searchCount,
        fetchCount: r.fetchCount,
        iterations: r.iterations,
      });
      console.log(`✗ JSON parse failed (s=${r.searchCount} f=${r.fetchCount})`);
    } else {
      newResults.push({
        ...r.parsed,
        status: 'ok',
        usage: r.usage,
        searchCount: r.searchCount,
        fetchCount: r.fetchCount,
        iterations: r.iterations,
      });
      console.log(
        `✓ ${r.parsed.grade ?? '?'} score=${r.parsed.total_score ?? '?'} ` +
          `s=${r.searchCount} f=${r.fetchCount} cost=$${r.cost.toFixed(4)}`,
      );
    }
  } catch (e) {
    newResults.push({ code: c.code, name: c.name, status: 'error', error: e.message });
    console.log(`✗ ${e.message}`);
  }
  await new Promise((r) => setTimeout(r, 1000));
}

// 合并：保留原 OK，覆盖原 ERR
const okMap = new Map(EXISTING.assessments.filter((a) => a.status === 'ok').map((a) => [a.code, a]));
const newMap = new Map(newResults.map((a) => [a.code, a]));
const merged = [];
for (const a of EXISTING.assessments) {
  merged.push(newMap.get(a.code) || okMap.get(a.code) || a);
}

const finalCost = parseFloat(EXISTING.summary?.total_cost_usd || '0') + totalCost;
writeJson('data/quality_scores_doubao_searxng_fetch.json', {
  fetchedAt: timestamp(),
  provider: 'doubao_searxng_fetch',
  model: 'doubao-seed-1-6-250615+searxng+jina',
  summary: {
    total: merged.length,
    ok: merged.filter((a) => a.status === 'ok').length,
    error: merged.filter((a) => a.status === 'error').length,
    total_cost_usd: finalCost.toFixed(4),
  },
  assessments: merged,
});

console.log('---');
console.log(`重跑成本: $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(2)})`);
console.log(`累计成本: $${finalCost.toFixed(4)} (~¥${(finalCost * 7.2).toFixed(2)})`);
console.log(`OK 总数: ${merged.filter((a) => a.status === 'ok').length}/${merged.length}`);
