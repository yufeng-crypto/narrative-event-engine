/**
 * Anthropic Claude API 调用封装。
 *
 * 价格（2026-04 参考，per 1M tokens）：
 * - claude-haiku-4-5：input $1.00 / output $5.00
 * - claude-sonnet-4-5：input $3.00 / output $15.00
 * - claude-opus-4-5：input $15.00 / output $75.00
 *
 * 默认 sonnet（稳定 + 中文金融知识 + 结构化输出）。
 * 复杂深度推理切 opus；批量结构化任务可考虑 haiku。
 *
 * API 文档：https://docs.anthropic.com/en/api/messages
 */

const ENDPOINT = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2023-06-01';

const MODEL_PRICING = {
  'claude-haiku-4-5': { in: 1.0, out: 5.0 },
  'claude-sonnet-4-5': { in: 3.0, out: 15.0 },
  'claude-opus-4-5': { in: 15.0, out: 75.0 },
};

/**
 * 调用 Claude，返回纯文本结果。
 *
 * @param {Object} opts
 * @param {string} opts.system - System prompt
 * @param {string} opts.user - User message
 * @param {string} [opts.model='claude-sonnet-4-5']
 * @param {number} [opts.temperature=0.2]
 * @param {number} [opts.maxTokens=4096]
 * @param {boolean} [opts.json=false] - 是否要求 JSON 输出（通过 prompt 强化）
 * @param {number} [opts.timeoutMs=120000]
 * @returns {Promise<{ text: string, usage: {input_tokens, output_tokens} }>}
 */
export async function callClaude({
  system,
  user,
  model = 'claude-sonnet-4-5',
  temperature = 0.2,
  maxTokens = 4096,
  json = false,
  timeoutMs = 120000,
}) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      'ANTHROPIC_API_KEY not set. Export it or put it in stock project root .env file.',
    );
  }

  // Anthropic Messages API 没有 response_format，靠 prompt 约束 JSON
  const finalSystem = json
    ? `${system}\n\n⚠️ 输出必须是合法 JSON，不包含任何 JSON 外的文本（不要 markdown 代码块包裹）。`
    : system;

  const body = {
    model,
    max_tokens: maxTokens,
    temperature,
    ...(finalSystem ? { system: finalSystem } : {}),
    messages: [{ role: 'user', content: user }],
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': ANTHROPIC_VERSION,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`Claude HTTP ${res.status}: ${text.slice(0, 500)}`);
    }

    const j = await res.json();
    // Anthropic 响应格式：content 是 array，取第一个 text block
    const text =
      j?.content?.find((c) => c.type === 'text')?.text ??
      j?.content?.[0]?.text ??
      '';
    const usage = j?.usage ?? {};
    return { text, usage, model };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 估算调用成本（仅供日志显示）。
 */
export function estimateClaudeCost(usage, model = 'claude-sonnet-4-5') {
  const r = MODEL_PRICING[model] ?? MODEL_PRICING['claude-sonnet-4-5'];
  const inTokens = usage?.input_tokens ?? 0;
  const outTokens = usage?.output_tokens ?? 0;
  return ((inTokens * r.in) + (outTokens * r.out)) / 1_000_000;
}
