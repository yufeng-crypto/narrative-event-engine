/**
 * Jina Reader 封装。
 *
 * 用法：fetchUrl('https://example.com/doc.pdf') → markdown
 *
 * 公益版：r.jina.ai/<url>，无需 API key，rate limit ~20/min。
 * 注册版：env JINA_API_KEY=xxx，Authorization Bearer header，rate ~200/min。
 *
 * 适合：
 *   - 中文财报/公告 HTML（巨潮、上交所、深交所）
 *   - PDF（Jina 内置转 markdown，但表格可能丢）
 *
 * 不适合：
 *   - SPA（如 fhsp.com.cn）— 此时走 Crawl4AI
 */

const JINA_BASE = 'https://r.jina.ai';

/**
 * @param {string} url 目标 URL
 * @param {Object} [opts]
 * @param {number} [opts.timeoutMs=30000]
 * @param {number} [opts.maxChars=30000] 截断阈值（防 LLM context 爆炸）
 * @param {boolean} [opts.keepLinks=false] 保留 markdown 链接（默认精简掉）
 * @returns {Promise<{ url, status, markdown, length, truncated }>}
 */
export async function fetchUrl(url, opts = {}) {
  const { timeoutMs = 30000, maxChars = 30000, keepLinks = false } = opts;
  const apiKey = process.env.JINA_API_KEY;

  const target = `${JINA_BASE}/${url}`;
  const headers = {
    Accept: 'text/markdown',
  };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  if (!keepLinks) headers['X-Retain-Images'] = 'none';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(target, { headers, signal: controller.signal });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      return {
        url,
        status: res.status,
        markdown: '',
        length: 0,
        truncated: false,
        error: `Jina HTTP ${res.status}: ${txt.slice(0, 300)}`,
      };
    }
    const md = await res.text();
    const truncated = md.length > maxChars;
    return {
      url,
      status: 200,
      markdown: truncated ? md.slice(0, maxChars) : md,
      length: md.length,
      truncated,
    };
  } catch (e) {
    return {
      url,
      status: 0,
      markdown: '',
      length: 0,
      truncated: false,
      error: e.name === 'AbortError' ? `timeout after ${timeoutMs}ms` : e.message,
    };
  } finally {
    clearTimeout(timer);
  }
}
