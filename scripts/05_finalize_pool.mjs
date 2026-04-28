/**
 * Stage 5 · 整合 final pool（基于 Stage 4 评估 + Opus tier 分级）
 *
 * 输入：
 *   - data/quality_scores.json (full pipeline)
 *   - data/quality_scores_current_pool.json (99 review)
 *
 * 输出：
 *   - data/final_pool.json
 *
 * 逻辑：
 *   - 合并两份 quality scores（去重）
 *   - 按 tier 分级：core / supporting / watch
 *     · core: A+ 级 + 现实可建仓的（grade A+ 或 A 且 current_yield > buy 阈值）
 *     · supporting: A 级，但有特殊 caveat（如 180202 越秀到期归零、508098 关联方）
 *     · watch: A 低（21-22 分），与 core 重叠或边际不足
 */

import { readFileSync, existsSync } from 'node:fs';
import { writeJson, timestamp } from './_lib/io.mjs';

const FULL_PIPELINE = 'data/quality_scores.json';
const CURRENT_POOL = 'data/quality_scores_current_pool.json';
const OUT = 'data/final_pool.json';

// Opus tier overrides (基于 methodology/05_stage5_review_2026-04-28.md)
// 不能 100% 自动化的部分：哪个标的因为特殊风险降一档
const TIER_OVERRIDES = {
  '180202': { tier: 'supporting', reason: '特许经营权 2036 到期归零，应当 11 年期高息债处理而非永续' },
  '508098': { tier: 'supporting', reason: '100% 关联方租户（京东自用）— 京东经营恶化即直接影响' },
  '180602': { tier: 'watch', reason: '与 180601 同消费类，且 2024-04 才上市分红刚起步' },
  '508058': { tier: 'watch', reason: '非厦门核心地段（集美区），覆盖率 104% 偏低' },
  '561580': { tier: 'watch', reason: '上市仅 1.5 年，运营记录太短' },
  '515100': { tier: 'watch', reason: '与 512890 同 A 股红利低波，二选一即可' },
};

const SUBTYPE_LABEL = {
  consumption: '消费',
  rental_housing: '保租房',
  energy: '能源',
  transportation: '交通',
  logistics: '物流',
  park: '产业园',
  municipal: '市政',
};

function tierFromGrade(grade) {
  if (grade === 'A+') return 'core';
  if (grade === 'A') return 'supporting';
  return 'watch';
}

function loadAssessments(path) {
  if (!existsSync(path)) return [];
  const j = JSON.parse(readFileSync(path, 'utf8'));
  return (j.assessments ?? []).filter((a) => a.status === 'ok');
}

function main() {
  const full = loadAssessments(FULL_PIPELINE);
  const cur = loadAssessments(CURRENT_POOL);
  console.log(`合并 quality_scores.json (${full.length}) + current_pool (${cur.length})`);

  // 用 code 去重，full pipeline 优先（更新）
  const byCode = new Map();
  for (const a of cur) byCode.set(a.code, a);
  for (const a of full) byCode.set(a.code, a);
  const merged = [...byCode.values()];
  console.log(`合并后唯一标的: ${merged.length}`);

  const enriched = merged.map((a) => {
    const baseTier = tierFromGrade(a.grade);
    const override = TIER_OVERRIDES[a.code];
    const tier = override?.tier ?? baseTier;
    const tierReason = override?.reason ?? null;
    return {
      code: a.code,
      name: a.name,
      grade: a.grade,
      total_score: a.total_score,
      tier,
      tier_reason: tierReason,
      subtype: a.fact_anchor?.underlying_asset
        ? null
        : null,
      fact_anchor: a.fact_anchor,
      red_flags: a.red_flags ?? [],
      upgrade_triggers: a.upgrade_triggers ?? [],
      recommendation: a.recommendation,
      verification_confidence: a.fact_anchor?.verification_confidence ?? 'unknown',
    };
  });

  // 排序：core > supporting > watch；每档内按 total_score 降序
  const tierOrder = { core: 0, supporting: 1, watch: 2 };
  enriched.sort(
    (a, b) => tierOrder[a.tier] - tierOrder[b.tier] || b.total_score - a.total_score,
  );

  const counts = {
    core: enriched.filter((p) => p.tier === 'core').length,
    supporting: enriched.filter((p) => p.tier === 'supporting').length,
    watch: enriched.filter((p) => p.tier === 'watch').length,
  };

  writeJson(OUT, {
    fetchedAt: timestamp(),
    summary: {
      total: enriched.length,
      ...counts,
      a_plus: enriched.filter((p) => p.grade === 'A+').length,
      a: enriched.filter((p) => p.grade === 'A').length,
    },
    notes: {
      methodology: 'methodology/05_stage5_review_2026-04-28.md',
      tier_overrides_explained: TIER_OVERRIDES,
    },
    pool: enriched,
  });

  console.log(`\n✅ 已写入 ${OUT}`);
  console.log(`   core: ${counts.core}, supporting: ${counts.supporting}, watch: ${counts.watch}`);
  console.log('\n=== 最终池 ===');
  console.log(
    'tier'.padEnd(12) + 'code'.padEnd(8) + 'grade'.padEnd(6) + 'score'.padEnd(6) + 'name',
  );
  console.log('-'.repeat(70));
  for (const p of enriched) {
    console.log(
      p.tier.padEnd(12) +
        p.code.padEnd(8) +
        p.grade.padEnd(6) +
        String(p.total_score).padEnd(6) +
        p.name,
    );
  }
}

main();
