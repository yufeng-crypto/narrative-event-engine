/**
 * Doubao（豆包）API 封装。
 * 端点：火山引擎 Ark / OpenAI-兼容 Chat Completions。
 *
 * 价格（2026-04 参考，per 1M tokens）：
 *   - doubao-1-5-pro-32k-250115：~¥0.8 input / ¥2 output
 *   - doubao-seed-1-6-250615：约同档（更新版本）
 * 比 Sonnet 便宜约 8x，比 DeepSeek 略贵但中文 + 时效性更新更好
 */

const ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions';

const MODEL_PRICING = {
  'doubao-1-5-pro-32k-250115': { in: 0.11, out: 0.28 }, // USD per 1M tokens
  'doubao-seed-1-6-250615': { in: 0.11, out: 0.28 },
};

/**
 * @param {Object} opts
 * @param {string} opts.system
 * @param {string} opts.user
 * @param {string} [opts.model='doubao-seed-1-6-250615']
 * @param {number} [opts.temperature=0.2]
 * @param {number} [opts.maxTokens=4096]
 * @param {boolean} [opts.json=false]
 * @param {number} [opts.timeoutMs=120000]
 */
export async function callDoubao({
  system,
  user,
  model = 'doubao-seed-1-6-250615',
  temperature = 0.2,
  maxTokens = 4096,
  json = false,
  timeoutMs = 120000,
}) {
  const apiKey = process.env.DOUBAO_API_KEY;
  if (!apiKey) {
    throw new Error('DOUBAO_API_KEY not set');
  }

  // Doubao API 没有 native JSON mode，靠 prompt 约束
  const finalSystem = json
    ? `${system}\n\n⚠️ 输出必须是合法 JSON，不包含任何 JSON 外的文本（不要 markdown 代码块包裹）。`
    : system;

  const body = {
    model,
    temperature,
    max_tokens: maxTokens,
    messages: [
      ...(finalSystem ? [{ role: 'system', content: finalSystem }] : []),
      { role: 'user', content: user },
    ],
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`Doubao HTTP ${res.status}: ${text.slice(0, 500)}`);
    }

    const j = await res.json();
    const text = j?.choices?.[0]?.message?.content ?? '';
    const usage = j?.usage ?? {};
    return { text, usage, model };
  } finally {
    clearTimeout(timer);
  }
}

export function estimateDoubaoCost(usage, model = 'doubao-seed-1-6-250615') {
  const r = MODEL_PRICING[model] ?? MODEL_PRICING['doubao-seed-1-6-250615'];
  const inT = usage?.prompt_tokens ?? 0;
  const outT = usage?.completion_tokens ?? 0;
  return ((inT * r.in) + (outT * r.out)) / 1_000_000;
}
