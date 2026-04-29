/**
 * Stage 4 · LLM 资产质量评估
 *
 * 输入：data/screened.json + methodology/04_quality_framework.md
 * 输出：data/quality_scores.json
 *
 * 对每只 candidate 调一次 LLM API，按 framework 6 维度评分。
 *
 * Provider 通过环境变量 LLM_PROVIDER 控制：
 *   - "deepseek" (默认): deepseek-chat V3，便宜（~¥0.01/只）
 *   - "claude-sonnet": Claude Sonnet 4.5，中文金融知识更深，幻觉率更低（~¥0.10/只）
 *   - "claude-haiku": Claude Haiku 4.5，便宜但 niche 知识弱（~¥0.03/只）
 *   - "claude-opus": Claude Opus 4.5，最强但杀鸡用牛刀（~¥0.50/只）
 *
 * 失败容忍：单只失败不中断，标记 status: 'error' 留在结果里。
 */

import { readFileSync } from 'node:fs';
import { readJson, writeJson, timestamp } from './_lib/io.mjs';
import { callDeepSeek, estimateCost as estimateDeepSeekCost } from './_lib/deepseek.mjs';
import { callClaude, estimateClaudeCost } from './_lib/claude.mjs';

const IN = 'data/screened.json';
const FRAMEWORK_PATH = 'methodology/04_quality_framework.md';
const PROVIDER = process.env.LLM_PROVIDER || 'deepseek';
const OUT_BY_PROVIDER = {
  'deepseek': 'data/quality_scores.json',
  'claude-haiku': 'data/quality_scores_claude_haiku.json',
  'claude-sonnet': 'data/quality_scores_claude_sonnet.json',
  'claude-opus': 'data/quality_scores_claude_opus.json',
};
const OUT = OUT_BY_PROVIDER[PROVIDER] || 'data/quality_scores.json';

const CLAUDE_MODEL_MAP = {
  'claude-haiku': 'claude-haiku-4-5',
  'claude-sonnet': 'claude-sonnet-4-5',
  'claude-opus': 'claude-opus-4-5',
};

async function callLLM(opts) {
  if (PROVIDER === 'deepseek') {
    const { text, usage } = await callDeepSeek(opts);
    return { text, usage, cost: estimateDeepSeekCost(usage), model: 'deepseek-chat' };
  }
  const claudeModel = CLAUDE_MODEL_MAP[PROVIDER];
  if (!claudeModel) {
    throw new Error(`Unknown LLM_PROVIDER: ${PROVIDER}. Use deepseek|claude-haiku|claude-sonnet|claude-opus`);
  }
  const { text, usage, model } = await callClaude({ ...opts, model: claudeModel });
  return { text, usage, cost: estimateClaudeCost(usage, claudeModel), model };
}

const SYSTEM_PROMPT = `你是公募 REITs 和红利 ETF 的资产质量分析师。你的任务是按 framework 给定的 6 个维度评分。

⚠️ 反幻觉规则（最重要！）：

很多 REIT 名字相似，底层资产容易混淆。在评分前**必须先**输出 \`fact_anchor\` 字段，包含 5 个核心事实：
1. 底层资产名称（具体到项目，如"青岛万象城"或"汉孝高速"）
2. 底层资产所在地（具体到城市/省）
3. 原始权益人（项目原始持有方）
4. 基金管理人
5. 上市日期（年月即可）

如果这 5 项里有任何一项你不确定，**整个标的的评估必须 abort**，输出：
- fact_anchor: 各字段填实际可查的，不确定的写 "unknown"
- grade: "INCOMPLETE"
- recommendation: "exclude"
- 各维度 score: null
- reasoning: "底层资产事实未确认，无法评分"

只有 5 项 fact_anchor 都能基于公开信息确定，才进入 6 维评分。

✅ 评分规则：
1. 每维度 reasoning 1-3 句话；evidence 必须**引用可核查的来源**（年报/季报/公告 + 具体日期或文档名，不能写"招募说明书显示..."这种泛泛的）
2. 不确定的维度写 score: null + "信息不足"，绝不瞎猜
3. ETF 类标的的 contract_stability 直接给 3 分（不适用）
4. 陌生标的保守评 3 分，不要给陌生标的盲打 5 分
5. 输出必须是合法 JSON

输出 JSON schema：
{
  "code": "string",
  "name": "string",
  "fact_anchor": {
    "underlying_asset": "string or 'unknown'",
    "asset_location": "string or 'unknown'",
    "original_owner": "string or 'unknown'",
    "fund_manager": "string or 'unknown'",
    "listing_date": "YYYY-MM or 'unknown'",
    "verification_confidence": "high|medium|low"
  },
  "scores": {
    "asset_quality":      { "score": 0-5 或 null, "reasoning": "string", "evidence": ["具体公告/年报名+日期"] },
    "contract_stability": { "score": 0-5 或 null, "reasoning": "string", "evidence": [...] },
    "operator_strength":  { "score": 0-5 或 null, "reasoning": "string", "evidence": [...] },
    "financial_health":   { "score": 0-5 或 null, "reasoning": "string", "evidence": [...] },
    "regulatory_risk":    { "score": 0-5 或 null, "reasoning": "string", "evidence": [...] },
    "growth_potential":   { "score": 0-5 或 null, "reasoning": "string", "evidence": [...] }
  },
  "total_score": 0-30 或 null,
  "grade": "A+|A|B+|B|C|D|INCOMPLETE",
  "recommendation": "include|watch|exclude",
  "red_flags": ["string"],
  "upgrade_triggers": ["string"]
}`;

function buildUserPrompt(candidate, framework) {
  return `请按以下 framework 评估这只标的：

═══════════════ FRAMEWORK ═══════════════
${framework}

═══════════════ 待评估标的 ═══════════════
代码：${candidate.code}
名称：${candidate.name}
类别：${candidate.category}${candidate.reit_subtype ? `（${candidate.reit_subtype}）` : ''}
上市时长：${candidate.listing_years} 年
规模：${candidate.aum_yi} 亿元
TTM 分红：${candidate.ttm_dividend} 元/份
当前股息率/分派率：${candidate.current_yield_pct}%
3 年股息率均值：${candidate.three_year_avg_yield_pct}%
最大回撤：${candidate.max_drawdown_pct}%
历史分位（当前 yield 在自身历史的位置）：${candidate.historical_percentile}%
量化筛选得分：${candidate.total_score}/100

请基于你对这只标的底层资产、运营方、财务情况的了解，按 framework 评分。
输出严格遵循上述 JSON schema。不要包含任何 JSON 外的解释文本。`;
}

async function main() {
  const screened = readJson(IN);
  const framework = readFileSync(FRAMEWORK_PATH, 'utf8');
  const candidates = screened.candidates.filter((c) => c.passed_to_stage4);
  console.log(`[04] Provider: ${PROVIDER}`);
  console.log(`[04] ${candidates.length} 只 candidates 进入质量评估`);
  console.log(`[04] 输出 → ${OUT}`);

  if (candidates.length === 0) {
    console.log('[04] ⚠️ 没有 candidates，跳过');
    process.exit(0);
  }

  const results = [];
  let totalCost = 0;
  let modelUsed = null;

  for (let i = 0; i < candidates.length; i++) {
    const c = candidates[i];
    process.stdout.write(`[04] (${i + 1}/${candidates.length}) ${c.code} ${c.name}... `);
    try {
      const { text, usage, cost, model } = await callLLM({
        system: SYSTEM_PROMPT,
        user: buildUserPrompt(c, framework),
        json: true,
        timeoutMs: 120000,
      });
      modelUsed = model;
      totalCost += cost;

      // 容错：去掉可能的 markdown code fence
      let cleaned = text.trim();
      if (cleaned.startsWith('```')) {
        cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      }

      let parsed;
      try {
        parsed = JSON.parse(cleaned);
      } catch (e) {
        results.push({
          code: c.code,
          name: c.name,
          status: 'error',
          error: 'JSON parse failed',
          raw: cleaned.slice(0, 1500),
        });
        console.log(`✗ JSON parse failed`);
        continue;
      }

      results.push({ ...parsed, status: 'ok', usage });
      console.log(
        `✓ ${parsed.grade ?? '?'} score=${parsed.total_score ?? '?'} ` +
          `confidence=${parsed.fact_anchor?.verification_confidence ?? '?'} ` +
          `cost=$${cost.toFixed(4)}`,
      );
    } catch (e) {
      results.push({
        code: c.code,
        name: c.name,
        status: 'error',
        error: e.message,
      });
      console.log(`✗ ${e.message}`);
    }
    // 节流，避免 API rate limit
    await sleep(500);
  }

  writeJson(OUT, {
    fetchedAt: timestamp(),
    provider: PROVIDER,
    model: modelUsed,
    summary: {
      total: candidates.length,
      ok: results.filter((r) => r.status === 'ok').length,
      error: results.filter((r) => r.status === 'error').length,
      total_cost_usd: totalCost.toFixed(4),
    },
    assessments: results,
  });
  console.log(`[04] ✅ 已写入 ${OUT}`);
  console.log(`[04] 💰 总成本: $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(2)})`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error('[04] ❌ Failed:', e);
  process.exit(1);
});
