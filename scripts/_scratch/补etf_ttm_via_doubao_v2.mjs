/**
 * v2：直接让 Doubao 用训练数据回答 ETF 的 TTM 分红
 * v1 失败原因：fhsp 是 SPA 不渲染表格 / Doubao timeout
 *
 * 策略：
 *   - 一次问 Doubao 一只 ETF 的"过去 12 个月分红总额"
 *   - 让 Doubao 给 confidence 自评
 *   - 不知道的标 null
 */

import { callDoubao } from '../_lib/doubao.mjs';

const ETF_CODES = {
  '515080': '中证红利ETF招商',
  '515300': '300红利低波ETF嘉实',
  '515890': '红利ETF博时',
  '560020': '红利ETF汇添富',
  '530880': '红利国企ETF银河',
  '510720': '红利国企ETF国泰',
  '563890': '国企红利ETF创金合信',
  '561060': '国企红利ETF华安',
  '563180': '高股息ETF银华',
  '159307': '红利低波ETF博时',
  '159549': '红利低波ETF天弘',
  '159581': '红利ETF万家',
  '159515': '国企红利ETF鹏扬',
  '159708': '红利ETF西部利得',
  '159589': '红利ETF广发',
  '520890': '港股通红利低波ETF华泰柏瑞',
  '520810': '港股通红利ETF易方达',
  '159117': '港股通红利低波ETF鹏华',
  '159118': '港股通红利低波ETF华夏',
};

async function processCode(code, name) {
  const userPrompt = `查询 A 股 / 港股 ETF "${name}"（代码 ${code}）的分红记录。

任务：基于你的训练数据知识，给出该 ETF 在 2025 年（特别是 2025-04 到 2025-12）的分红总额（元/份）。

⚠️ 要求：
- 仅基于你确实知道的训练数据，不要编造
- 不知道就老实标 null
- 如果你只知道部分（如只知 2025 H1），分别列出
- 确认这是 ETF 不是其他基金

输出 JSON：
{
  "code": "${code}",
  "name_confirmed": "string (你认为的实际名字)",
  "ttm_dividend_2025": <number 或 null，2025 全年分红总额>,
  "individual_dividends_known": [
    { "ex_date": "YYYY-MM-DD", "amount_per_share": <number> }
  ],
  "confidence": "high|medium|low",
  "knowledge_cutoff_note": "string (你训练数据覆盖到何时)",
  "is_etf": true|false
}

⚠️ 只输出 JSON，无 markdown 代码块。`;

  try {
    const { text, usage } = await callDoubao({
      system: '你是金融数据助手。基于训练数据如实回答，不知道就标 null。严格输出 JSON。',
      user: userPrompt,
      json: true,
      timeoutMs: 60000,
    });
    let cleaned = text.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }
    const parsed = JSON.parse(cleaned);
    return { ...parsed, usage };
  } catch (e) {
    return { code, name, ttm_dividend_2025: null, error: e.message };
  }
}

async function main() {
  const results = [];
  let totalCost = 0;
  const codes = Object.keys(ETF_CODES);

  for (let i = 0; i < codes.length; i++) {
    const code = codes[i];
    const name = ETF_CODES[code];
    process.stdout.write(`[${i + 1}/${codes.length}] ${code} ${name}... `);
    const r = await processCode(code, name);
    results.push(r);
    if (r.ttm_dividend_2025 != null) {
      console.log(`✓ ${r.ttm_dividend_2025} (${r.individual_dividends_known?.length ?? 0} 次, ${r.confidence})`);
    } else {
      console.log(`✗ null (${r.error || '不知道'})`);
    }
    if (r.usage) {
      const cost = (r.usage.prompt_tokens ?? 0) * 0.11e-6 + (r.usage.completion_tokens ?? 0) * 0.28e-6;
      totalCost += cost;
    }
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log(`\n💰 总成本: $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(2)})\n`);
  console.log('=== JSON 片段（合并到 manual_dividend_overrides.json）===');
  for (const r of results) {
    if (r.ttm_dividend_2025 != null && r.confidence !== 'low') {
      const conf = `, "confidence": "${r.confidence}"`;
      const lastDate = r.individual_dividends_known?.at(-1)?.ex_date ?? '2025-12-31';
      console.log(
        `    "${r.code}": { "ttm_dividend": ${r.ttm_dividend_2025}, "as_of": "${lastDate}", "verified_by": "doubao_training_data_${r.individual_dividends_known?.length ?? 0}div"${conf}, "notes": "${r.knowledge_cutoff_note?.slice(0, 60) ?? ''}" },`,
      );
    } else {
      console.log(`    "${r.code}": { "ttm_dividend": null, "as_of": "2026-04-30", "verified_by": "doubao_unknown", "notes": "${r.confidence ?? 'low'}, ${r.knowledge_cutoff_note?.slice(0, 60) ?? r.error ?? ''}" },`);
    }
  }
}

main().catch((e) => { console.error('Failed:', e); process.exit(1); });
