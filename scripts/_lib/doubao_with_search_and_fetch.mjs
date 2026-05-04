/**
 * Phase 2 评估器：Doubao + SearXNG search + Jina Reader fetch。
 *
 * 比 Phase 1 多了一个工具 `fetch_page`，让 Doubao 拿到 search snippet 后能
 * 主动深读高价值 URL（年报/公告/财报章节），从而挖到 Phase 1 漏掉的深层事实
 * （如商誉减值、特许权到期、超额分配、扩募终止等）。
 *
 * 工具预算：≤8 search + ≤4 fetch
 *
 * 成本估算（per 标的）：
 *   - 输入 token: ~250K-400K（含 fetch 拉来的 markdown）
 *   - 输出: ~3K
 *   - Doubao: ~¥0.30-0.50
 *   - Jina: 0（公益版）
 *
 * 比 Phase 1 (~¥0.06) 贵 5-8x，但仍是 Sonnet (~¥10-20) 的 1/30。
 */

import { searxngSearch } from './searxng.mjs';
import { fetchUrl } from './jina_reader.mjs';
import { callDoubaoWithMessages, estimateDoubaoCost } from './doubao.mjs';

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search_web',
      description:
        '搜索中文金融信息（财经新闻 / 年报 / 公告 / 季报）。返回前 8 条结果的标题、URL、摘要（≤250 字）。摘要不够时用 fetch_page 深读。',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: '查询字符串。建议含：标的代码 + 名称 + 年份 + 主题词',
          },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'fetch_page',
      description:
        '深读单个 URL 的全文 markdown（最多 30K 字符）。用于 search snippet 不够时挖深层事实。优先 fetch：年报关键章节页、公告原文（巨潮/上交所/搜狐财经）、扩募/解禁公告。**最多调用 4 次**，慎用。',
      parameters: {
        type: 'object',
        properties: {
          url: {
            type: 'string',
            description: '要深读的 URL（必须是 search_web 返回过的 URL，避免乱猜）',
          },
        },
        required: ['url'],
      },
    },
  },
];

// Stage A：调研阶段 system prompt（不要求 JSON，只要求收齐证据）
const STAGE_A_SYSTEM = `你是公募 REITs / 红利 ETF 的 Stage 4 资产质量分析师。本阶段任务是调研：用 search_web + fetch_page 工具收齐评分所需的事实，**不要输出 JSON**，调研完成后用结构化文本汇总即可。

【⚠️ 严格预算】
- search_web ≤ 8 次
- fetch_page ≤ 4 次
- 总迭代 ≤ 14 轮

【调研重点（按优先级）】
1. **fact_anchor 验证**：底层资产名称 / 位置 / 原始权益人 / 基金管理人 / 上市日期
   - 如果用户已提供 known_fact_anchor，跳过这一步，直接进 2
2. **基础财务**：2024 年报 + 2025 季报的 NOI / 可分配金额 / 出租率
3. **深层风险（关键）**：负面关键词搜索（按需，不强制全做）
   - 商誉减值 / 资产减值
   - 净利润下降 / 净亏损
   - 扩募终止 / 关联交易 / 解禁
   - 超额分配 / 分红覆盖率
   - 特许经营权剩余年限 / 到期归零
4. **fetch 触发条件**：search snippet 出现具体数字 / 关键事件 → fetch URL 验证
   - 优先 fetch：财经媒体解读（搜狐/新浪/睿思网） > 巨潮/上交所公告 > 基金官网

【调研完成后输出格式（plain text，不要 JSON）】
=== FACT_ANCHOR ===
underlying_asset: ...
asset_location: ...
original_owner: ...
fund_manager: ...
listing_date: YYYY-MM
verification_confidence: high|medium|low

=== KEY FACTS ===
（把所有重要事实列出来，每条配证据来源 + 日期，例：）
- 2024 净利润 -9889 万元，因商誉减值 1.13 亿元 [来源：2025-03-27 搜狐财经年报解读]
- 2025Q1 出租率 86.37%，环比 -3% [来源：2025Q1 季报]
- 2025-09-01 解禁 1.55 亿份，占总份额 31% [来源：解禁公告]

=== RED FLAGS ===
（最重要的风险，每条带具体数字+日期）

=== UPGRADE TRIGGERS ===
（什么条件触发上调）

=== SEARCH/FETCH LOG ===
search_queries: ["...", "..."]
fetched_urls: ["...", "..."]`;

// Stage B：JSON 化阶段 system prompt（短 input + 短 output，避免 truncate）
const STAGE_B_SYSTEM = `你是 JSON 格式化助手。给你 Stage A 调研结果，按 schema 输出严格 JSON，不要任何 JSON 外的文字（不要 markdown 代码块）。

【评分规则提醒】
- 每维度 0-5 分；ETF 类标的 contract_stability=3；不确定写 score: null + reasoning: "信息不足"
- total_score = 6 维之和（0-30）
- grade 映射：26+ A+ / 23-25 A / 21-22 A- / 19-20 B+ / 17-18 B / 15-16 B- / 13-14 C+ / 11-12 C / ≤10 D
- INCOMPLETE 等级仅用于 fact_anchor 全 unknown 且无法兜底时

【JSON Schema】
{
  "code": "string",
  "name": "string",
  "search_queries_used": ["..."],
  "fetched_urls": ["..."],
  "fact_anchor": {
    "underlying_asset": "string",
    "asset_location": "string",
    "original_owner": "string",
    "fund_manager": "string",
    "listing_date": "YYYY-MM",
    "verification_confidence": "high|medium|low"
  },
  "scores": {
    "asset_quality":      { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] },
    "contract_stability": { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] },
    "operator_strength":  { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] },
    "financial_health":   { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] },
    "regulatory_risk":    { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] },
    "growth_potential":   { "score": 0-5或null, "reasoning": "≤50字", "evidence": ["..."] }
  },
  "total_score": 0-30或null,
  "grade": "A+|A|A-|B+|B|B-|C+|C|D|INCOMPLETE",
  "recommendation": "include|watch|exclude",
  "red_flags": ["具体事实+数字+日期"],
  "upgrade_triggers": ["..."]
}`;

function buildStageAUserPrompt(candidate, knownFactAnchor) {
  const seedBlock = knownFactAnchor
    ? `

【⚠️ Phase 1 已验证的 fact_anchor，直接采纳，不要再 search 验证】
${JSON.stringify(knownFactAnchor, null, 2)}

请把 search 预算全部用于挖深层风险（财务异常 / 特许权 / 扩募 / 解禁 / 关联交易），不要重复验证 fact_anchor。`
    : '';

  return `请调研以下标的，用 search_web + fetch_page 收齐 Stage 4 评估所需的事实。

代码：${candidate.code}
名称：${candidate.name}
类别：${candidate.category}${candidate.reit_subtype ? `（${candidate.reit_subtype}）` : ''}
TTM 分红：${candidate.ttm_dividend} 元/份
当前分派率：${candidate.current_yield_pct}%
当前价：${candidate.current_price ?? '—'}
量化筛选得分：${candidate.total_score ?? '—'}/100${seedBlock}

**预算：≤8 search + ≤4 fetch**。调研完成后用 plain text 列出 fact_anchor + key facts + red flags + upgrade triggers + search/fetch log。**不要输出 JSON**。`;
}

function buildStageBUserPrompt(candidate, stageAResult, knownFactAnchor) {
  const seedBlock = knownFactAnchor
    ? `

【已锁定 fact_anchor（Phase 1 验证，直接采纳）】
${JSON.stringify(knownFactAnchor, null, 2)}`
    : '';

  return `请把以下 Stage A 调研结果转换为严格 JSON。

【标的基础信息】
code: ${candidate.code}
name: ${candidate.name}
category: ${candidate.category}${candidate.reit_subtype ? ` (${candidate.reit_subtype})` : ''}${seedBlock}

【Stage A 调研结果】
${stageAResult}

按 system prompt 里的 JSON Schema 输出。注意：
1. 每个维度 reasoning ≤ 50 字
2. evidence 数组里只放最关键的 1-3 条
3. red_flags ≤ 5 条，每条带数字+日期
4. 输出纯 JSON，无 markdown 包裹`;
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
    const r = await fetchUrl(args.url, { maxChars: 25000 });
    if (r.error) {
      return { url: args.url, error: r.error };
    }
    return {
      url: args.url,
      length: r.length,
      truncated: r.truncated,
      markdown: r.markdown,
    };
  }
  return { error: `Unknown tool: ${name}` };
}

/**
 * Phase 2 评估单只标的（两阶段：search/fetch 调研 → JSON 化）。
 * @param {Object} candidate
 * @param {Object} [opts]
 * @param {Object} [opts.knownFactAnchor] - Phase 1 已验证的 fact_anchor，注入后跳过重新搜索
 * @param {number} [opts.maxIterations=14]
 * @param {number} [opts.maxSearches=8]
 * @param {number} [opts.maxFetches=4]
 * @param {boolean} [opts.verbose=false]
 * @returns {Promise<{ raw, stageA, parsed, parseError, usage, cost, searchCount, fetchCount, iterations }>}
 */
export async function evaluateWithSearchAndFetch(candidate, opts = {}) {
  const {
    knownFactAnchor,
    maxIterations = 14,
    maxSearches = 8,
    maxFetches = 4,
    verbose = false,
  } = opts;

  // ============== Stage A：调研（tool loop）==============
  const messages = [
    { role: 'system', content: STAGE_A_SYSTEM },
    { role: 'user', content: buildStageAUserPrompt(candidate, knownFactAnchor) },
  ];

  let totalCost = 0;
  let totalTokens = 0;
  let searchCount = 0;
  let fetchCount = 0;
  let iterations = 0;
  let finalText = '';

  for (let i = 1; i <= maxIterations; i++) {
    iterations = i;
    let resp;
    let lastErr;
    // 加 3 次重试容忍偶发的 fetch failed / network blip
    for (let retry = 0; retry < 3; retry++) {
      try {
        resp = await callDoubaoWithMessages({
          messages,
          tools: TOOLS,
          maxTokens: 8192, // 上调避免 JSON 输出截断
          timeoutMs: 180000, // stage A 单轮超时 3 分钟（fetch 多时上下文大）
        });
        lastErr = null;
        break;
      } catch (e) {
        lastErr = e;
        if (verbose) console.log(`  [iter ${i}] retry ${retry + 1}/3: ${e.message}`);
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
          `tool_calls=${resp.tool_calls?.length ?? 0} ` +
          `cost=$${cost.toFixed(4)}`,
      );
    }

    if (!resp.tool_calls || resp.tool_calls.length === 0) {
      finalText = resp.content;
      break;
    }

    messages.push({
      role: 'assistant',
      content: resp.content || null,
      tool_calls: resp.tool_calls,
    });

    for (const call of resp.tool_calls) {
      const isSearch = call.function.name === 'search_web';
      const isFetch = call.function.name === 'fetch_page';

      // 预算检查
      if (isSearch && searchCount >= maxSearches) {
        messages.push({
          role: 'tool',
          tool_call_id: call.id,
          content: JSON.stringify({
            error: 'search budget exhausted',
            message: `已用 search ${maxSearches} 次。请基于已有信息直接输出 JSON，或改用 fetch_page。`,
          }),
        });
        continue;
      }
      if (isFetch && fetchCount >= maxFetches) {
        messages.push({
          role: 'tool',
          tool_call_id: call.id,
          content: JSON.stringify({
            error: 'fetch budget exhausted',
            message: `已用 fetch ${maxFetches} 次。请基于已读内容输出 JSON。`,
          }),
        });
        continue;
      }

      let args = {};
      try {
        args = JSON.parse(call.function.arguments);
      } catch {}
      let result;
      try {
        result = await dispatchTool(call.function.name, args);
        if (isSearch) searchCount++;
        if (isFetch) fetchCount++;
        if (verbose) {
          if (isSearch) {
            console.log(
              `    🔍 "${args.query?.slice(0, 50) ?? '?'}" → ${result.count ?? 0} results`,
            );
          } else if (isFetch) {
            console.log(
              `    📄 "${(args.url || '').slice(0, 60)}" → ${
                result.error ? '✗ ' + result.error.slice(0, 50) : (result.length / 1000).toFixed(1) + 'K chars'
              }`,
            );
          }
        }
      } catch (e) {
        result = { error: e.message };
      }
      messages.push({
        role: 'tool',
        tool_call_id: call.id,
        content: JSON.stringify(result),
      });
    }
  }

  // ============== Stage B：JSON 化（独立调用，无 tools）==============
  const stageAResult = finalText || '(Stage A 没有返回结果)';

  let parsed = null;
  let parseError = null;
  let stageBRaw = '';

  // Stage B 重试：最多 3 次，每次超时 / 退避独立配置
  // Doubao 在 stage A 上下文较大时 stage B 单次响应可能 60-150s，给充足窗口
  const STAGE_B_TIMEOUTS = [180000, 240000, 240000]; // 3min / 4min / 4min
  for (let attempt = 0; attempt < STAGE_B_TIMEOUTS.length; attempt++) {
    try {
      const stageB = await callDoubaoWithMessages({
        messages: [
          { role: 'system', content: STAGE_B_SYSTEM },
          { role: 'user', content: buildStageBUserPrompt(candidate, stageAResult, knownFactAnchor) },
        ],
        // 不带 tools — 强制纯文本输出
        maxTokens: 8192,
        timeoutMs: STAGE_B_TIMEOUTS[attempt],
      });
      const stageBCost = estimateDoubaoCost(stageB.usage);
      totalCost += stageBCost;
      totalTokens += stageB.usage?.total_tokens ?? 0;
      stageBRaw = stageB.content || '';

      let cleaned = stageBRaw.trim();
      if (cleaned.startsWith('```')) {
        cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      }
      parsed = JSON.parse(cleaned);
      parseError = null;
      if (verbose) console.log(`  [stage B] attempt ${attempt + 1} tokens=${stageB.usage?.total_tokens} cost=$${stageBCost.toFixed(4)} ✓`);
      break;
    } catch (e) {
      parseError = e.message;
      if (verbose) console.log(`  [stage B] attempt ${attempt + 1}/${STAGE_B_TIMEOUTS.length} failed: ${e.message}`);
      await new Promise((r) => setTimeout(r, 2000 + attempt * 1500));
    }
  }

  // ============== Fix 3：fact_anchor 兜底 ==============
  // 如果 LLM 返回的 fact_anchor 全 unknown 但 knownFactAnchor 已提供，强制用 seed
  if (parsed?.fact_anchor && knownFactAnchor) {
    const fa = parsed.fact_anchor;
    const allUnknown =
      fa.underlying_asset === 'unknown' &&
      fa.asset_location === 'unknown' &&
      fa.original_owner === 'unknown';
    if (allUnknown) {
      parsed.fact_anchor = { ...knownFactAnchor, source: 'phase1_fallback' };
      parsed._fact_anchor_fallback = true;
      if (verbose) console.log(`  [fact_anchor] fallback to Phase 1 seed`);
    }
  }

  return {
    raw: finalText,           // Stage A plain text
    stageBRaw,                // Stage B JSON raw
    parsed,
    parseError,
    usage: { total_tokens: totalTokens },
    cost: totalCost,
    searchCount,
    fetchCount,
    iterations,
    seeded: !!knownFactAnchor,
  };
}
