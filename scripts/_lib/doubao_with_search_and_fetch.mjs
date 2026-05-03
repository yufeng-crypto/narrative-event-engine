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

const SYSTEM_PROMPT = `你是公募 REITs / 红利 ETF 的 Stage 4 资产质量分析师，使用 search_web + fetch_page 工具调研后输出严格 JSON 评估。

【⚠️ 严格预算】
- search_web ≤ 8 次
- fetch_page ≤ 4 次（用于 search snippet 不够时深读年报/公告原文）
- 总迭代 ≤ 14 轮

【⚠️ 反幻觉硬规则】
- fact_anchor 5 字段每个必须有 search/fetch 证据，不确定写 "unknown"
- red_flags 必须配具体数字 + 日期，不是泛泛之谈
- 评分基于 search/fetch 找到的事实，不基于训练数据印象

【流程建议】
1. search 1-2：拿 fact_anchor 5 字段（资产 / 位置 / 原始权益人 / 基金管理人 / 上市日）
2. search 3-4：拿 2024 年报 + 2025 季报关键数字（NOI / 可分配金额 / 出租率）
3. **search 5-7（强制）：必须做至少 3 次"负面关键词"搜索**，挖深层风险：
   - "代码 名称 商誉减值 资产减值"
   - "代码 名称 净利润下降 净亏损"
   - "代码 名称 扩募终止 关联交易 解禁"
   - "代码 名称 超额分配 分红覆盖率"
   - "代码 名称 特许经营权 到期 年限"
   不要全跳过这一步，REIT 风险藏在这里。
4. search 8（可选）：补漏 / 验证矛盾信息
5. **fetch（关键）：snippet 里看到这些信号必须 fetch 那个 URL**：
   - 净利润 / 净亏损 / 商誉减值 + 具体数字（例 -9889 万）
   - 扩募终止 / 出租率下滑 / 关联交易披露
   - 财经媒体解读（搜狐/新浪/睿思网/华尔街见闻），通常比官网更具体
   - 优先级：财经媒体 > 巨潮资讯/上交所公告 > 基金官网（官网信息往往最浅）
6. 综合输出 JSON

【判断 search vs fetch 的指南】
- 仅需"是不是 / 有没有 / 大致多少"→ search 够
- 需要"具体数字 / 完整公告内容 / 章节细节"→ fetch
- snippet 已经给出明确数字 → 不要再 fetch（省预算）
- snippet 含糊或矛盾 → fetch 验证
- snippet 出现负面关键词（亏损 / 减值 / 终止 / 下滑）→ **必须 fetch 验证**

【最终输出 JSON Schema（不带 markdown 代码块）】
{
  "code": "...",
  "name": "...",
  "search_queries_used": ["..."],
  "fetched_urls": ["..."],
  "fact_anchor": {
    "underlying_asset": "...",
    "asset_location": "...",
    "original_owner": "...",
    "fund_manager": "...",
    "listing_date": "YYYY-MM",
    "verification_confidence": "high|medium|low"
  },
  "scores": {
    "asset_quality": { "score": 0-5, "reasoning": "...", "evidence": ["..."] },
    "contract_stability": { "score": 0-5, "reasoning": "...", "evidence": ["..."] },
    "operator_strength": { "score": 0-5, "reasoning": "...", "evidence": ["..."] },
    "financial_health": { "score": 0-5, "reasoning": "...", "evidence": ["..."] },
    "regulatory_risk": { "score": 0-5, "reasoning": "...", "evidence": ["..."] },
    "growth_potential": { "score": 0-5, "reasoning": "...", "evidence": ["..."] }
  },
  "total_score": 0-30,
  "grade": "A+|A|A-|B+|B|B-|C+|C|D",
  "recommendation": "include|watch|exclude",
  "red_flags": ["具体事实 + 数字 + 日期"],
  "upgrade_triggers": ["..."]
}`;

function buildUserPrompt(candidate) {
  return `请评估以下标的的 Stage 4 质量评估。**必须先用 search_web + fetch_page 调研**，不要凭训练数据答。

代码：${candidate.code}
名称：${candidate.name}
类别：${candidate.category}${candidate.reit_subtype ? `（${candidate.reit_subtype}）` : ''}
TTM 分红：${candidate.ttm_dividend} 元/份
当前分派率：${candidate.current_yield_pct}%
当前价：${candidate.current_price ?? '—'}
量化筛选得分：${candidate.total_score ?? '—'}/100

**预算：≤8 search + ≤4 fetch**。规划好查询，找到 fact_anchor + 6 维评分材料 + 深层 red_flags 后立即输出。`;
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
 * Phase 2 评估单只标的（search + fetch）。
 * @param {Object} candidate
 * @param {Object} [opts]
 * @param {number} [opts.maxIterations=14]
 * @param {number} [opts.maxSearches=8]
 * @param {number} [opts.maxFetches=4]
 * @param {boolean} [opts.verbose=false]
 * @returns {Promise<{ raw, parsed, parseError, usage, cost, searchCount, fetchCount, iterations }>}
 */
export async function evaluateWithSearchAndFetch(candidate, opts = {}) {
  const {
    maxIterations = 14,
    maxSearches = 8,
    maxFetches = 4,
    verbose = false,
  } = opts;

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: buildUserPrompt(candidate) },
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
          timeoutMs: 120000,
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

  let parsed = null;
  let parseError = null;
  let cleaned = finalText.trim();
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
  }
  try {
    parsed = JSON.parse(cleaned);
  } catch (e) {
    parseError = e.message;
  }

  return {
    raw: finalText,
    parsed,
    parseError,
    usage: { total_tokens: totalTokens },
    cost: totalCost,
    searchCount,
    fetchCount,
    iterations,
  };
}
