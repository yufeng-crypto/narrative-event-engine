/**
 * DeepSeek API 调用封装。
 *
 * DeepSeek API 是 OpenAI-compatible，不需要装 SDK，直接 fetch 即可。
 * 价格（2026-04 参考）：
 * - deepseek-chat (V3)：input $0.27 / output $1.10 per 1M tokens
 * - deepseek-reasoner (R1)：input $0.55 / output $2.19 per 1M tokens
 *
 * 默认用 deepseek-chat（V3），快、便宜、对结构化任务足够。
 * 如果 Stage 4 评估发现 V3 给的 reasoning 不够深入，可改 deepseek-reasoner。
 */

const ENDPOINT = 'https://api.deepseek.com/chat/completions';

/**
 * 调用 DeepSeek，返回纯文本结果。
 *
 * @param {Object} opts
 * @param {string} opts.system - System prompt
 * @param {string} opts.user - User message
 * @param {string} [opts.model='deepseek-chat']
 * @param {number} [opts.temperature=0.2]
 * @param {boolean} [opts.json=false] - 是否要求 JSON 输出
 * @param {number} [opts.timeoutMs=60000]
 * @returns {Promise<{ text: string, usage: {prompt_tokens, completion_tokens, total_tokens} }>}
 */
export async function callDeepSeek({
  system,
  user,
  model = 'deepseek-chat',
  temperature = 0.2,
  json = false,
  timeoutMs = 60000,
}) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    throw new Error(
      'DEEPSEEK_API_KEY not set. Copy your key into stock project root .env file.',
    );
  }

  const body = {
    model,
    temperature,
    messages: [
      ...(system ? [{ role: 'system', content: system }] : []),
      { role: 'user', content: user },
    ],
  };
  if (json) {
    body.response_format = { type: 'json_object' };
  }

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
      throw new Error(`DeepSeek HTTP ${res.status}: ${text.slice(0, 500)}`);
    }

    const json = await res.json();
    const text = json?.choices?.[0]?.message?.content ?? '';
    const usage = json?.usage ?? {};
    return { text, usage };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 估算调用成本（仅供日志显示用）。
 */
export function estimateCost(usage, model = 'deepseek-chat') {
  const rates = {
    'deepseek-chat': { in: 0.27, out: 1.10 },
    'deepseek-reasoner': { in: 0.55, out: 2.19 },
  };
  const r = rates[model] ?? rates['deepseek-chat'];
  const cost =
    ((usage.prompt_tokens ?? 0) * r.in +
      (usage.completion_tokens ?? 0) * r.out) /
    1_000_000;
  return cost; // USD
}
