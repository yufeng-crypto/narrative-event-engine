/**
 * 临时脚本：用现有 lib/products.ts 里的 12 只标的作为 candidates 跑 Stage 4。
 * 用于 push2 限流时快速验证 Stage 4 framework 在多标的上的表现。
 *
 * 完整流水线建立后，这个脚本可以删除，由 screen:01-04 替代。
 */

import { readFileSync } from 'node:fs';
import { writeJson, timestamp } from './_lib/io.mjs';
import { callDeepSeek, estimateCost } from './_lib/deepseek.mjs';

const FRAMEWORK_PATH = 'methodology/04_quality_framework.md';
const OUT = 'data/quality_scores_current_pool.json';

// 直接 hardcode 12 只 — 元数据来自 lib/products.ts
const CURRENT_POOL = [
  { code: '515100', name: '红利低波 100 ETF（景顺长城）', category: 'dividend_etf_a', listing_years: 5.5, ttm_dividend: 0.064, current_yield_pct: 4.41, current_price: 1.451 },
  { code: '512890', name: '红利低波 ETF（华泰柏瑞）', category: 'dividend_etf_a', listing_years: 7.5, ttm_dividend: 0.060, current_yield_pct: 5.03, current_price: 1.192 },
  { code: '510880', name: '上证红利 ETF（华泰柏瑞）', category: 'dividend_etf_a', listing_years: 19.5, ttm_dividend: 0.142, current_yield_pct: 4.27, current_price: 3.325 },
  { code: '561580', name: '央企红利 ETF（华泰柏瑞）', category: 'dividend_etf_a', listing_years: 1.5, ttm_dividend: 0.05, current_yield_pct: 3.97, current_price: 1.258 },
  { code: '513530', name: '港股通红利 ETF（华泰柏瑞 QDII）', category: 'dividend_etf_hk', listing_years: 4.5, ttm_dividend: 0.10, current_yield_pct: 5.99, current_price: 1.669 },
  { code: '180601', name: '华夏华润商业 REIT', category: 'reit', reit_subtype: 'consumption', listing_years: 2.2, ttm_dividend: 0.3651, current_yield_pct: 3.64, current_price: 10.031 },
  { code: '180602', name: '中金印力消费 REIT', category: 'reit', reit_subtype: 'consumption', listing_years: 2.0, ttm_dividend: 0.0856, current_yield_pct: 2.05, current_price: 4.185 },
  { code: '180202', name: '华夏越秀高速 REIT', category: 'reit', reit_subtype: 'transportation', listing_years: 4.4, ttm_dividend: 0.38175, current_yield_pct: 7.04, current_price: 5.42 },
  { code: '508077', name: '华夏基金华润有巢 REIT', category: 'reit', reit_subtype: 'rental_housing', listing_years: 2.5, ttm_dividend: 0.13, current_yield_pct: 4.75, current_price: 2.737 },
  { code: '508058', name: '中金厦门安居 REIT', category: 'reit', reit_subtype: 'rental_housing', listing_years: 1.8, ttm_dividend: 0.12, current_yield_pct: 3.00, current_price: 4.001 },
  { code: '508028', name: '中信建投国家电投新能源 REIT', category: 'reit', reit_subtype: 'energy', listing_years: 3.1, ttm_dividend: 0.30, current_yield_pct: 2.91, current_price: 10.312 },
  { code: '508098', name: '嘉实京东仓储基础设施 REIT', category: 'reit', reit_subtype: 'logistics', listing_years: 3.3, ttm_dividend: 0.18, current_yield_pct: 5.14, current_price: 3.499 },
];

const SYSTEM_PROMPT = `你是公募 REITs 和红利 ETF 的资产质量分析师。你的任务是按 framework 给定的 6 个维度评分。

⚠️ 反幻觉规则（最重要！）：

很多 REIT/ETF 名字相似，底层资产容易混淆。在评分前**必须先**输出 fact_anchor 字段，包含 5 个核心事实：
1. 底层资产名称（具体到项目，如"青岛万象城"或"汉孝高速"）
2. 底层资产所在地（具体到城市/省）
3. 原始权益人（项目原始持有方）
4. 基金管理人
5. 上市日期（年月即可）

⚠️ 注意：REIT 的"基金名"和"底层资产位置"可能不一致！
例如"华夏越秀高速 REIT"的"越秀"是原始权益人（越秀集团），底层资产其实在湖北武汉（汉孝高速）。
"华夏华润商业 REIT"的"华润"是品牌方，底层是青岛万象城。
不要被名字误导，必须基于实际项目认定底层资产。

如果这 5 项里有任何一项你不确定，整个标的的评估必须 abort：
- fact_anchor: 各字段填实际可查的，不确定的写 "unknown"
- grade: "INCOMPLETE"
- recommendation: "exclude"
- 各维度 score: null

✅ 评分规则：
1. 每维度 reasoning 1-3 句话；evidence 必须**引用可核查的来源**（年报/季报/公告 + 具体日期或文档名）
2. 不确定的维度写 score: null + reasoning: "信息不足"，不要瞎猜
3. ETF 类标的：contract_stability 直接给 3 分（不适用），reasoning 写 "ETF 不适用"
4. 陌生标的保守评 3 分

输出 JSON schema:
{
  "code": "string",
  "name": "string",
  "fact_anchor": {
    "underlying_asset": "string",
    "asset_location": "string",
    "original_owner": "string",
    "fund_manager": "string",
    "listing_date": "YYYY-MM",
    "verification_confidence": "high|medium|low"
  },
  "scores": {
    "asset_quality": { "score": 0-5 或 null, "reasoning": "string", "evidence": ["string"] },
    "contract_stability": {...},
    "operator_strength": {...},
    "financial_health": {...},
    "regulatory_risk": {...},
    "growth_potential": {...}
  },
  "total_score": 0-30 或 null,
  "grade": "A+|A|B+|B|C|D|INCOMPLETE",
  "recommendation": "include|watch|exclude",
  "red_flags": ["string"],
  "upgrade_triggers": ["string"]
}`;

function buildUserPrompt(c, framework) {
  return `请按以下 framework 评估这只标的：

═══════════════ FRAMEWORK ═══════════════
${framework}

═══════════════ 待评估标的 ═══════════════
代码：${c.code}
名称：${c.name}
类别：${c.category}${c.reit_subtype ? `（${c.reit_subtype}）` : ''}
上市时长：${c.listing_years} 年
TTM 分红：${c.ttm_dividend} 元/份
当前股息率/分派率：${c.current_yield_pct}%
当前价格：${c.current_price}

请基于公开信息按 framework 评分。先输出 fact_anchor 锚定底层事实，再评 6 个维度。
输出严格遵循 JSON schema，不要包含任何 JSON 外的解释文本。`;
}

async function main() {
  const framework = readFileSync(FRAMEWORK_PATH, 'utf8');
  console.log(`[99] 评估当前 pool ${CURRENT_POOL.length} 只标的...`);

  const results = [];
  let totalCost = 0;
  for (let i = 0; i < CURRENT_POOL.length; i++) {
    const c = CURRENT_POOL[i];
    process.stdout.write(`[99] (${i + 1}/${CURRENT_POOL.length}) ${c.code} ${c.name}... `);
    try {
      const { text, usage } = await callDeepSeek({
        system: SYSTEM_PROMPT,
        user: buildUserPrompt(c, framework),
        json: true,
        timeoutMs: 90000,
      });
      const cost = estimateCost(usage);
      totalCost += cost;
      try {
        const parsed = JSON.parse(text);
        results.push({ ...parsed, status: 'ok', usage });
        console.log(
          `✓ ${parsed.grade ?? '?'} score=${parsed.total_score ?? '?'} ` +
            `confidence=${parsed.fact_anchor?.verification_confidence ?? '?'} ` +
            `cost=$${cost.toFixed(4)}`,
        );
      } catch (e) {
        results.push({ code: c.code, name: c.name, status: 'parse_error', raw: text.slice(0, 500) });
        console.log(`✗ parse error`);
      }
    } catch (e) {
      results.push({ code: c.code, name: c.name, status: 'api_error', error: e.message });
      console.log(`✗ ${e.message}`);
    }
    await sleep(500);
  }

  writeJson(OUT, {
    fetchedAt: timestamp(),
    summary: {
      total: CURRENT_POOL.length,
      ok: results.filter((r) => r.status === 'ok').length,
      total_cost_usd: totalCost.toFixed(4),
    },
    assessments: results,
  });
  console.log(`\n[99] ✅ 已写入 ${OUT}`);
  console.log(`[99] 💰 总成本: $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(2)})`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error('[99] ❌ Failed:', e);
  process.exit(1);
});
