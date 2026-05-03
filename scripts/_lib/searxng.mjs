/**
 * SearXNG 客户端封装。
 * 假设本地 docker 部署在 localhost:8890，JSON API 已启用。
 *
 * 配置参考（settings.yml）：
 *   server: { limiter: false }
 *   search: { formats: [html, json], default_lang: zh-CN }
 */

const DEFAULT_BASE = process.env.SEARXNG_URL || 'http://localhost:8890';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

/**
 * @param {string} query
 * @param {Object} [opts]
 * @param {number} [opts.topN=10] 返回前 N 条
 * @param {string[]} [opts.engines] 限定引擎（如 ['baidu','google']）
 * @param {number} [opts.timeoutMs=15000]
 * @returns {Promise<{ query, count, results: Array<{title,url,content,engine}> }>}
 */
export async function searxngSearch(query, opts = {}) {
  const { topN = 10, engines, timeoutMs = 15000 } = opts;
  const url = new URL(`${DEFAULT_BASE}/search`);
  url.searchParams.set('q', query);
  url.searchParams.set('format', 'json');
  url.searchParams.set('pageno', '1');
  if (engines && engines.length > 0) {
    url.searchParams.set('engines', engines.join(','));
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url.toString(), {
      headers: { 'User-Agent': UA, Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(`SearXNG HTTP ${res.status}`);
    }
    const j = await res.json();
    return {
      query: j.query ?? query,
      count: j.results?.length ?? 0,
      results: (j.results || []).slice(0, topN).map((r) => ({
        title: r.title ?? '',
        url: r.url ?? '',
        content: r.content ?? '',
        engine: r.engine ?? '',
      })),
    };
  } finally {
    clearTimeout(timer);
  }
}
