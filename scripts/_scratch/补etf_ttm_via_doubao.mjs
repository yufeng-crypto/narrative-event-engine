/**
 * 一次性脚本：用 Node.js 拉 fundf10 HTML + Doubao 解析，补 19 个 ETF 的 TTM 分红
 *
 * 流程：
 *   1. 对每个 ETF code, fetch https://fundf10.eastmoney.com/fhsp_<code>.html
 *   2. 提取分红表格 HTML 区段（避免发整页给 Doubao）
 *   3. 让 Doubao 解析为结构化 JSON
 *   4. 输出汇总到 stdout，人工审后合并到 manual_dividend_overrides.json
 *
 * 用法：node --env-file=.env scripts/_scratch/补etf_ttm_via_doubao.mjs
 */

import { callDoubao } from '../_lib/doubao.mjs';

const ETF_CODES = {
  // A 股红利 ETF（缺 override 的）
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
  // 港股红利 ETF（缺 override 的）
  '520890': '港股通红利低波ETF华泰柏瑞',
  '520810': '港股通红利ETF易方达',
  '159117': '港股通红利低波ETF鹏华',
  '159118': '港股通红利低波ETF华夏',
};

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  Referer: 'https://fundf10.eastmoney.com/',
};

async function fetchFhspHtml(code) {
  const url = `https://fundf10.eastmoney.com/fhsp_${code}.html`;
  const res = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(15000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

/** 抽取分红送配相关的表格 HTML 段（避免发整页 60KB 给 Doubao） */
function extractDividendSection(html) {
  // 找 fhinfo 相关的 div
  const fhMatch = html.match(/<div[^>]*class="[^"]*fhinfo[^"]*"[^>]*>[\s\S]*?<\/div>\s*<\/div>/);
  if (fhMatch) return fhMatch[0];
  // fallback：找含"分红"的 table
  const tableMatch = html.match(/<table[^>]*>[\s\S]{0,80}?分红[\s\S]*?<\/table>/);
  if (tableMatch) return tableMatch[0];
  // 再 fallback：取中间 10KB
  return html.slice(20000, 35000);
}

async function processCode(code, name) {
  let html;
  try {
    html = await fetchFhspHtml(code);
  } catch (e) {
    return { code, name, ttm_dividend: null, error: `fetch failed: ${e.message}` };
  }
  const section = extractDividendSection(html);

  const systemPrompt = `你是 HTML 解析助手，从基金分红送配 HTML 中提取分红记录。严格输出 JSON。`;
  const userPrompt = `从下面这段基金分红 HTML 中提取**除息日（除权除息日 / ex_date）在 2025-04-30 至 2026-04-30 之间**的所有分红记录，
计算 TTM 累计每份分红（元）。

⚠️ 规则：
- 只看"每份分红"金额，不要"基金总分红"
- 不要看 2025-04-30 之前或 2026-04-30 之后的
- 如果该基金从未分红，ttm_dividend = null
- 如果 HTML 里看不到清晰的分红表格（如 SPA 没渲染），ttm_dividend = null + reason: "html_not_rendered"

输出 JSON schema（严格遵循，不要 markdown 代码块）：
{
  "code": "${code}",
  "name": "${name}",
  "ttm_dividend": <number 或 null>,
  "individual_dividends": [
    { "ex_date": "YYYY-MM-DD", "amount_per_share": <number> }
  ],
  "confidence": "high|medium|low",
  "reason": "string (可选，说明 null 原因)"
}

待解析 HTML：
${section.slice(0, 8000)}`;

  try {
    const { text, usage } = await callDoubao({
      system: systemPrompt,
      user: userPrompt,
      json: true,
      timeoutMs: 30000,
    });
    let cleaned = text.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }
    const parsed = JSON.parse(cleaned);
    return { ...parsed, usage };
  } catch (e) {
    return { code, name, ttm_dividend: null, error: `doubao failed: ${e.message}` };
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
    if (r.ttm_dividend != null) {
      console.log(`✓ ttm=${r.ttm_dividend} (${r.individual_dividends?.length ?? 0} 次, ${r.confidence})`);
    } else {
      console.log(`✗ null (${r.reason || r.error || 'no data'})`);
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
    if (r.ttm_dividend != null) {
      const conf = r.confidence ? `, "confidence": "${r.confidence}"` : '';
      const lastDate = r.individual_dividends?.at(-1)?.ex_date ?? '2026-04-30';
      console.log(
        `    "${r.code}": { "ttm_dividend": ${r.ttm_dividend}, "as_of": "${lastDate}", "verified_by": "doubao_html_parse_${r.individual_dividends?.length ?? 0}div"${conf} },`,
      );
    } else {
      console.log(`    "${r.code}": { "ttm_dividend": null, "as_of": "2026-04-30", "verified_by": "doubao_html_parse_failed", "notes": "${r.reason || r.error}" },`);
    }
  }
}

main().catch((e) => {
  console.error('Failed:', e);
  process.exit(1);
});
