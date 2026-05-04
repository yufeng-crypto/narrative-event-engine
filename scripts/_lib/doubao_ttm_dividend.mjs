/**
 * TTM 分红专用查询模块 — Doubao + SearXNG + Jina Reader。
 *
 * 不同于 Stage 4 评估（全维度+评分），这个模块只做一件事：
 * 找出某只 ETF/REIT 过去 12 个月的所有分红记录，累加 = TTM。
 *
 * 解决问题：manual_dividend_overrides.json 里很多 ETF 的 TTM 是估算的
 * （`verified_by: estimated_from_X%_yield`），需要替换成实测数据。
 *
 * 工具预算：≤6 search + ≤3 fetch（比 Stage 4 少，因为任务窄）
 * 成本：~¥0.05-0.10/只
 */

import { searxngSearch } from './searxng.mjs';
import { fetchUrl } from './jina_reader.mjs';
import { callDoubaoWithMessages, estimateDoubaoCost } from './doubao.mjs';

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search_web',
      description: '搜索分红公告 / 财经页面 / fundf10 等。返回前 8 条标题、URL、摘要。',
      parameters: {
        type: 'object',
        properties: { query: { type: 'string', description: '查询字符串' } },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'fetch_page',
      description: '深读单 URL 全文 markdown（最多 25K 字符）。用于查具体分红日期+金额表格。',
      parameters: {
        type: 'object',
        properties: { url: { type: 'string', description: '要 fetch 的 URL（必须是 search 返回过的）' } },
        required: ['url'],
      },
    },
  },
];

const STAGE_A_SYSTEM = `你是中文 ETF / REIT 分红数据查询助手。任务：找出某只标的过去 12 个月的全部分红记录。

【⚠️ 严格预算】
- search_web ≤ 6 次
- fetch_page ≤ 3 次
- 总迭代 ≤ 12 轮

【⚠️ 反幻觉硬规则】
- 每条分红必须有：具体除息日 (YYYY-MM-DD) + 每份分红金额 (元) + 数据来源 URL
- 不要凭训练数据估算或编造
- 找不全 → 标 confidence: medium 或 low，说明找到几条 + 时间范围

【优先信息源（按权威性）】
1. 基金管理人官网公告（华泰柏瑞 / 易方达 / 华夏基金 等）
2. fundf10.eastmoney.com/fhsp_<code>.html （东方财富分红记录页）
3. 上交所/深交所披露的"收益分配公告"
4. 财经媒体（搜狐 / 新浪 / 雪球）— 仅用作交叉验证

【流程建议】
1. search "代码 名称 分红记录 2025"
2. search "代码 fundf10 分红"
3. 找到分红列表页 → fetch_page 深读
4. 如果列表不全（少于预期次数），search 补漏
5. 校核：每次分红的"每份金额"加总 = TTM

【调研完成后输出格式（plain text，不要 JSON）】
=== TARGET ===
code: ...
name: ...
lookup_window: 2025-05-05 至 2026-05-05

=== DIVIDENDS ===
1. 除息日 YYYY-MM-DD, 每份金额 0.0XX 元, 来源: <URL>
2. 除息日 YYYY-MM-DD, 每份金额 0.0XX 元, 来源: <URL>
（按时间倒序）

=== TTM SUM ===
total: 0.0XXX 元/份
confidence: high|medium|low
notes: ...

=== SEARCH/FETCH LOG ===
queries: ["...", "..."]
fetches: ["URL1", "URL2"]`;

const STAGE_B_SYSTEM = `你是 JSON 格式化助手。把 Stage A 调研结果转换成严格 JSON。
不要输出任何 JSON 外的文本，不要 markdown 代码块。

【JSON Schema】
{
  "code": "string",
  "name": "string",
  "lookup_window": { "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" },
  "dividends": [
    { "ex_date": "YYYY-MM-DD", "amount_per_share": 0.0123, "source": "URL" }
  ],
  "ttm_dividend": 0.0489,
  "confidence": "high|medium|low",
  "notes": "string，找不到全部记录时说明情况；找到 N 条覆盖 M 个月等"
}

注意：
- ttm_dividend 必须等于 dividends 中所有 amount_per_share 的累加（保留 4 位小数）
- 如果一条分红都没找到，dividends 为空数组，ttm_dividend 为 null，confidence = low
`;

function buildStageAPrompt(target) {
  const today = new Date();
  const fromDate = new Date(today.getTime() - 365 * 86400000);
  const fromStr = fromDate.toISOString().slice(0, 10);
  const toStr = today.toISOString().slice(0, 10);

  return `请调研以下标的的过去 12 个月分红记录。

代码：${target.code}
名称：${target.name}
类别：${target.category || '未指定'}
查询窗口：${fromStr} 至 ${toStr}

预算：≤6 search + ≤3 fetch。每条分红必须有具体除息日 + 金额 + 来源 URL。
找不全也要诚实标 confidence，不要凭训练数据估算。`;
}

function buildStageBPrompt(stageAText) {
  return `Stage A 调研结果如下，请转成严格 JSON：

${stageAText}`;
}

async function dispatchTool(name, args) {
  if (name === 'search_web') {
    const r = await searxngSearch(args.query, { topN: 8 });
    return {
      query: r.query,
      count: r.count,
      results: r.results.map((x) => ({
        title: x.title,
        url: x.url,
        snippet: (x.content || '').slice(0, 250),
      })),
    };
  }
  if (name === 'fetch_page') {
    const r = await fetchUrl(args.url, { maxChars: 20000 });
    if (r.error) return { url: args.url, error: r.error };
    return { url: args.url, length: r.length, truncated: r.truncated, markdown: r.markdown };
  }
  return { error: `Unknown tool: ${name}` };
}

/**
 * 查询单只标的的 TTM 分红。
 * @param {Object} target - { code, name, category }
 * @param {Object} [opts] - { maxIterations, maxSearches, maxFetches, verbose }
 * @returns {Promise<{ raw, parsed, parseError, cost, searchCount, fetchCount, iterations }>}
 */
export async function lookupTTMDividend(target, opts = {}) {
  const { maxIterations = 12, maxSearches = 6, maxFetches = 3, verbose = false } = opts;

  const messages = [
    { role: 'system', content: STAGE_A_SYSTEM },
    { role: 'user', content: buildStageAPrompt(target) },
  ];

  let totalCost = 0;
  let totalTokens = 0;
  let searchCount = 0;
  let fetchCount = 0;
  let iterations = 0;
  let stageAText = '';

  // ============== Stage A：tool loop ==============
  for (let i = 1; i <= maxIterations; i++) {
    iterations = i;
    let resp;
    let lastErr;
    for (let retry = 0; retry < 3; retry++) {
      try {
        resp = await callDoubaoWithMessages({
          messages,
          tools: TOOLS,
          maxTokens: 4096,
          timeoutMs: 180000,
        });
        lastErr = null;
        break;
      } catch (e) {
        lastErr = e;
        await new Promise((r) => setTimeout(r, 2000 * (retry + 1)));
      }
    }
    if (lastErr) throw lastErr;

    const cost = estimateDoubaoCost(resp.usage);
    totalCost += cost;
    totalTokens += resp.usage?.total_tokens ?? 0;
    if (verbose) {
      console.log(
        `  [iter ${i}] tokens=${resp.usage?.total_tokens} ` +
          `tool_calls=${resp.tool_calls?.length ?? 0} cost=$${cost.toFixed(4)}`,
      );
    }

    if (!resp.tool_calls || resp.tool_calls.length === 0) {
      stageAText = resp.content || '';
      break;
    }

    messages.push({ role: 'assistant', content: resp.content || null, tool_calls: resp.tool_calls });

    for (const call of resp.tool_calls) {
      const isSearch = call.function.name === 'search_web';
      const isFetch = call.function.name === 'fetch_page';
      if (isSearch && searchCount >= maxSearches) {
        messages.push({
          role: 'tool',
          tool_call_id: call.id,
          content: JSON.stringify({ error: 'search budget exhausted', message: '请基于已有信息输出 plain text' }),
        });
        continue;
      }
      if (isFetch && fetchCount >= maxFetches) {
        messages.push({
          role: 'tool',
          tool_call_id: call.id,
          content: JSON.stringify({ error: 'fetch budget exhausted', message: '请基于已读输出 plain text' }),
        });
        continue;
      }
      let args = {};
      try { args = JSON.parse(call.function.arguments); } catch {}
      let result;
      try {
        result = await dispatchTool(call.function.name, args);
        if (isSearch) searchCount++;
        if (isFetch) fetchCount++;
        if (verbose) {
          if (isSearch) console.log(`    🔍 "${(args.query || '').slice(0, 50)}" → ${result.count ?? 0}`);
          else if (isFetch) console.log(`    📄 "${(args.url || '').slice(0, 60)}" → ${result.error ? '✗' : (result.length / 1000).toFixed(1) + 'K'}`);
        }
      } catch (e) {
        result = { error: e.message };
      }
      messages.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify(result) });
    }
  }

  // ============== Stage B：JSON 化 ==============
  let parsed = null;
  let parseError = null;
  let stageBRaw = '';
  const STAGE_B_TIMEOUTS = [120000, 180000, 180000];
  for (let attempt = 0; attempt < STAGE_B_TIMEOUTS.length; attempt++) {
    try {
      const stageB = await callDoubaoWithMessages({
        messages: [
          { role: 'system', content: STAGE_B_SYSTEM },
          { role: 'user', content: buildStageBPrompt(stageAText || '(Stage A 没有结果)') },
        ],
        maxTokens: 4096,
        timeoutMs: STAGE_B_TIMEOUTS[attempt],
      });
      const cost = estimateDoubaoCost(stageB.usage);
      totalCost += cost;
      totalTokens += stageB.usage?.total_tokens ?? 0;
      stageBRaw = stageB.content || '';
      let cleaned = stageBRaw.trim();
      if (cleaned.startsWith('```')) cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      parsed = JSON.parse(cleaned);
      parseError = null;
      if (verbose) console.log(`  [stage B] attempt ${attempt + 1} cost=$${cost.toFixed(4)} ✓`);
      break;
    } catch (e) {
      parseError = e.message;
      if (verbose) console.log(`  [stage B] attempt ${attempt + 1}/3 failed: ${e.message}`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  return {
    raw: stageAText,
    stageBRaw,
    parsed,
    parseError,
    cost: totalCost,
    usage: { total_tokens: totalTokens },
    searchCount,
    fetchCount,
    iterations,
  };
}
