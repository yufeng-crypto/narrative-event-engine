/**
 * 阶段 1 验证：Doubao + SearXNG（仅 search snippet，不 fetch URL）能否做出
 * 接近 Sonnet 内置 WebSearch 质量的 Stage 4 评估。
 *
 * 测试标的：508077 华夏华润有巢 REIT
 *   - Sonnet 已知答案：A 22 分，关键发现 = "2024 实际分配 6541万 > 可分配 4904万 (超额分配 33%)"
 *   - Doubao 之前无 web 评估：A 22 但漏掉超额分配（red_flags 0 个）
 *   - 看 Doubao + SearXNG 能不能找到这个关键事实
 *
 * 用法：node --env-file=.env scripts/_scratch/test_phase1_searxng.mjs
 */

import { readFileSync } from 'node:fs';
import {
  callDoubaoWithMessages,
  estimateDoubaoCost,
} from '../_lib/doubao.mjs';
import { searxngSearch } from '../_lib/searxng.mjs';

// ============================================================
// 工具定义（给 Doubao 看的 schema）
// ============================================================

const TOOLS = [
  {
    type: 'function',
    function: {
      name: 'search_web',
      description:
        '搜索中文金融信息（财经新闻/年报/分红公告/REIT 季报等）。返回前 8 条结果的标题、URL、内容摘要。优先用具体的查询词如"代码 名称 年度 关键词"。',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: '搜索查询，建议含：标的代码 + 名称 + 年份 + 主题词',
          },
        },
        required: ['query'],
      },
    },
  },
];

// ============================================================
// 系统 Prompt（要求 Doubao 用 SearXNG 验证 fact_anchor + 找最新风险）
// ============================================================

const SYSTEM_PROMPT = `你是公募 REITs / 红利 ETF 资产质量分析师，使用 search_web 工具调研后输出 Stage 4 评估。

【流程】
1. 先 search_web 验证 fact_anchor（5 个核心事实）：
   - 底层资产名称
   - 资产位置
   - 原始权益人
   - 基金管理人
   - 上市日期
2. 再 search_web 找最新（2024-2026）的 NOI / 可分配金额 / 出租率 / 重大公告
3. 最后输出 JSON 评估（fact_anchor + 6 维度评分 + red_flags + grade）

【关键约束】
- 必须真的调用 search_web 工具，不要凭训练数据答
- 每个 fact_anchor 字段必须有 search_web 结果支持，不确定写 "unknown"
- red_flags 必须是 search 找到的具体事实（含数字 / 日期），不是泛泛之谈

【最终输出 JSON Schema】（只在 search 验证后输出，不要 markdown 代码块）
{
  "code": "string",
  "name": "string",
  "search_queries_used": ["query1", "query2", ...],
  "fact_anchor": {
    "underlying_asset": "string",
    "asset_location": "string",
    "original_owner": "string",
    "fund_manager": "string",
    "listing_date": "YYYY-MM",
    "verification_confidence": "high|medium|low"
  },
  "scores": {
    "asset_quality": { "score": 0-5, "reasoning": "string", "evidence": ["search 找到的具体引用"] },
    "contract_stability": { "score": 0-5, "reasoning": "string", "evidence": [] },
    "operator_strength": { "score": 0-5, "reasoning": "string", "evidence": [] },
    "financial_health": { "score": 0-5, "reasoning": "string", "evidence": [] },
    "regulatory_risk": { "score": 0-5, "reasoning": "string", "evidence": [] },
    "growth_potential": { "score": 0-5, "reasoning": "string", "evidence": [] }
  },
  "total_score": 0-30,
  "grade": "A+|A|A-|B+|B|B-|C+|C|D",
  "recommendation": "include|watch|exclude",
  "red_flags": ["具体事实+数字+日期"],
  "upgrade_triggers": []
}`;

// ============================================================
// Tool dispatcher
// ============================================================

async function dispatchTool(name, args) {
  if (name === 'search_web') {
    const r = await searxngSearch(args.query, { topN: 8 });
    // 缩减返回大小给 LLM
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

// ============================================================
// 主流程：tool_use loop
// ============================================================

const TARGET = {
  code: '508077',
  name: '华夏基金华润有巢 REIT',
  category: 'reit',
  reit_subtype: 'rental_housing',
  ttm_dividend: 0.13,
  current_yield_pct: 4.75,
};

const USER_PROMPT = `请评估以下 REIT 的 Stage 4 质量评估。**必须**先用 search_web 工具调研，不要凭训练数据答。

代码：${TARGET.code}
名称：${TARGET.name}
类别：${TARGET.category} (${TARGET.reit_subtype})
TTM 分红：${TARGET.ttm_dividend} 元/份
当前分派率：${TARGET.current_yield_pct}%

调研重点：
1. 底层资产实际是什么（精确到项目名 + 城市）
2. 2024-2025 年最新可分配金额、NOI、出租率
3. 是否有"实际分配超过可分配金额"等异常财务行为
4. 重大公告（扩募 / 解禁 / 监管 / 运营变化）

完成所有 search 后再输出 JSON。`;

async function main() {
  console.log('='.repeat(70));
  console.log('阶段 1 验证：Doubao + SearXNG (仅 snippet)');
  console.log('目标：' + TARGET.code + ' ' + TARGET.name);
  console.log('对照 Sonnet 已知答案：A 22 分，发现"超额分配"问题');
  console.log('='.repeat(70));
  console.log('');

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: USER_PROMPT },
  ];

  const MAX_ITERS = 10;
  let totalCost = 0;
  let totalTokens = 0;
  let searchCount = 0;
  let finalText = '';

  for (let i = 1; i <= MAX_ITERS; i++) {
    console.log(`--- 第 ${i} 轮 LLM 调用 ---`);
    const resp = await callDoubaoWithMessages({
      messages,
      tools: TOOLS,
      timeoutMs: 90000,
    });
    const cost = estimateDoubaoCost(resp.usage);
    totalCost += cost;
    totalTokens += resp.usage?.total_tokens ?? 0;
    console.log(
      `tokens=${resp.usage?.total_tokens} cost=$${cost.toFixed(4)} ` +
        `tool_calls=${resp.tool_calls?.length ?? 0}`,
    );

    // 没 tool_call = 最终答案
    if (!resp.tool_calls || resp.tool_calls.length === 0) {
      finalText = resp.content;
      console.log('✅ 最终答案返回');
      break;
    }

    // 加 assistant 的 tool_use 消息
    messages.push({
      role: 'assistant',
      content: resp.content || null,
      tool_calls: resp.tool_calls,
    });

    // 执行每个 tool_call
    for (const call of resp.tool_calls) {
      const argsStr = call.function.arguments;
      let args;
      try {
        args = JSON.parse(argsStr);
      } catch (e) {
        args = {};
      }
      console.log(`  🔍 ${call.function.name}("${args.query ?? '?'}")`);
      let result;
      try {
        result = await dispatchTool(call.function.name, args);
        searchCount++;
        console.log(
          `     → ${result.count ?? 0} results (前 3 标题: ${(result.results || [])
            .slice(0, 3)
            .map((r) => r.title.slice(0, 30))
            .join(' | ')})`,
        );
      } catch (e) {
        result = { error: e.message };
        console.log(`     ✗ ${e.message}`);
      }
      messages.push({
        role: 'tool',
        tool_call_id: call.id,
        content: JSON.stringify(result),
      });
    }
  }

  console.log('');
  console.log('='.repeat(70));
  console.log(
    `总耗费：${searchCount} 次 search / ${totalTokens} tokens / $${totalCost.toFixed(4)} (~¥${(totalCost * 7.2).toFixed(3)})`,
  );
  console.log('='.repeat(70));
  console.log('');
  console.log('--- 最终输出 ---');
  console.log(finalText);
  console.log('');

  // 关键判断：是否找到"超额分配"问题
  const FOUND_OVER_DISTRIBUTION =
    /超额分配|超过可分配|实际分配.*>.*可分配|6541|4904/.test(finalText);
  console.log('='.repeat(70));
  console.log('🎯 关键判断：是否找到 Sonnet 标志性发现"超额分配"问题？');
  console.log(FOUND_OVER_DISTRIBUTION ? '✅ 找到了' : '❌ 没找到');
  console.log('='.repeat(70));
}

main().catch((e) => {
  console.error('Failed:', e);
  process.exit(1);
});
