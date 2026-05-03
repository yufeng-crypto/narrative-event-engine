/**
 * Doubao + SearXNG tool_use 评估器（Stage 4 替代 Sonnet WebSearch 的方案）。
 *
 * 用途：让 Doubao 通过工具调用 SearXNG，迭代搜索 + 综合得到 Stage 4 评估 JSON。
 * 结果质量已验证 ≈ Sonnet 内置 WebSearch（详见 _scratch/test_phase1_searxng.mjs）。
 *
 * 工作机制：
 *   1. system prompt 引导 Doubao 规划 search 次数（≤8）
 *   2. tool_use loop：Doubao 提出 search → 我们调 SearXNG → 结果回传
 *   3. 直到 Doubao 不再 tool_call，输出最终 JSON 评估
 *
 * 成本参考（per 标的，截至 2026-05）：
 *   - Doubao: ~¥0.20（200K tokens）
 *   - SearXNG: 0（自部署）
 *   - 总: ~¥0.20，约为 Sonnet 内置 WebSearch 一半
 */

import { searxngSearch } from './searxng.mjs';
import { callDoubaoWithMessages, estimateDoubaoCost } from './doubao.mjs';

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search_web',
      description:
        '搜索中文金融信息（财经新闻 / 年报 / 公告 / 季报）。返回前 8 条结果的标题、URL、摘要。',
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
];

const SYSTEM_PROMPT = `你是公募 REITs / 红利 ETF 的 Stage 4 评估师，使用 search_web 工具调研后输出严格 JSON 评估。

【⚠️ 严格约束】
- **search 预算 ≤ 8 次**（超出会被强制终止）
- 每次 search 用**复合查询**覆盖多个 fact（如"代码 名称 2024年报 可分配金额 出租率"）
- 不要重复同一查询；查不到就承认 unknown 而不是无限重试
- 找到信息后立即综合输出，不要"凑搜索次数"

【流程建议（最少需要 5 次 search 完成）】
search 1: "代码 名称 底层资产 项目"  → 拿 fact_anchor 5 个字段
search 2: "代码 2024年报 NOI 可分配金额 出租率"  → 财务健康
search 3: "代码 2025 季报 最新运营数据"  → 趋势变化
search 4: "代码 扩募 解禁 重大公告"  → 监管 + 成长
search 5: "代码 风险 问题"  → 红旗（可选）

【⚠️ 反幻觉硬规则】
- 每个 fact_anchor 字段必须有 search 结果支持，否则写 "unknown"
- red_flags 必须配具体数字 + 日期（"2024 可分配 -19.28%" ✅；"基本面恶化" ❌）
- 评分基于 search 找到的事实，不基于训练数据印象

【最终输出 JSON Schema（不带 markdown 代码块）】
{
  "code": "...",
  "name": "...",
  "search_queries_used": ["..."],
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
  return `请评估以下标的的 Stage 4 质量评估。**必须先用 search_web 调研**，不要凭训练数据答。

代码：${candidate.code}
名称：${candidate.name}
类别：${candidate.category}${candidate.reit_subtype ? `（${candidate.reit_subtype}）` : ''}
TTM 分红：${candidate.ttm_dividend} 元/份
当前分派率：${candidate.current_yield_pct}%
当前价：${candidate.current_price ?? '—'}
量化筛选得分：${candidate.total_score ?? '—'}/100

**搜索预算 ≤ 8 次**。规划好查询，每次复合查询多个 fact，找到 fact_anchor + 6 维评分材料后立即输出。`;
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
  return { error: `Unknown tool: ${name}` };
}

/**
 * 评估单只标的。
 * @param {Object} candidate - 含 code/name/category/ttm_dividend/current_yield_pct 等
 * @param {Object} [opts]
 * @param {number} [opts.maxIterations=10] LLM 调用最大轮数
 * @param {number} [opts.maxSearches=8] search 最大次数（硬上限，超出强制终止）
 * @param {boolean} [opts.verbose=false] 打印中间过程
 * @returns {Promise<{ result, parsed, usage, cost, searchCount, iterations }>}
 */
export async function evaluateWithSearch(candidate, opts = {}) {
  const { maxIterations = 10, maxSearches = 8, verbose = false } = opts;

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: buildUserPrompt(candidate) },
  ];

  let totalCost = 0;
  let totalTokens = 0;
  let searchCount = 0;
  let iterations = 0;
  let finalText = '';

  for (let i = 1; i <= maxIterations; i++) {
    iterations = i;
    const resp = await callDoubaoWithMessages({
      messages,
      tools: TOOLS,
      timeoutMs: 90000,
    });
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

    // 无 tool_call = 最终答案
    if (!resp.tool_calls || resp.tool_calls.length === 0) {
      finalText = resp.content;
      break;
    }

    messages.push({
      role: 'assistant',
      content: resp.content || null,
      tool_calls: resp.tool_calls,
    });

    // 检查 search budget
    if (searchCount >= maxSearches) {
      // 强制要求下一轮不再调工具
      messages.push({
        role: 'tool',
        tool_call_id: resp.tool_calls[0].id,
        content: JSON.stringify({
          error: 'search budget exhausted',
          message: `已达到 search 上限 ${maxSearches} 次。请基于已有信息立即输出 JSON 评估，不再调 search_web。`,
        }),
      });
      // 跳过本轮其他 tool_calls
      for (let k = 1; k < resp.tool_calls.length; k++) {
        messages.push({
          role: 'tool',
          tool_call_id: resp.tool_calls[k].id,
          content: JSON.stringify({ error: 'budget exhausted' }),
        });
      }
      continue;
    }

    for (const call of resp.tool_calls) {
      let args = {};
      try {
        args = JSON.parse(call.function.arguments);
      } catch {}
      let result;
      try {
        result = await dispatchTool(call.function.name, args);
        if (call.function.name === 'search_web') searchCount++;
        if (verbose) {
          console.log(
            `    🔍 "${args.query?.slice(0, 50) ?? '?'}" → ${result.count ?? 0} results`,
          );
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

  // 解析最终 JSON
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
    iterations,
  };
}
