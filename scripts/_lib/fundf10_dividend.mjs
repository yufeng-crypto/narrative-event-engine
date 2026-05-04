/**
 * 直接解析 fundf10.eastmoney.com/fhsp_<code>.html 的分红表格。
 *
 * 这个页面对 ETF / REIT / 公募基金都通用，格式稳定，是国内最权威的分红数据源
 * （东方财富聚合各基金公司公告 + 上交所/深交所披露）。
 *
 * 用法：const r = await fetchFundf10Dividends('512890');
 *   r.dividends = [{ year, register_date, ex_date, amount, pay_date }, ...]
 *   r.ttm_12m = 0.0xxx  // 过去 365 天累加
 *
 * 这是确定性解析（不依赖 LLM），TTM 抓得准。Doubao+SearXNG 可以作为兜底
 * （新发未上 fundf10 / 页面挂了时）。
 */

import { fetchUrl } from './jina_reader.mjs';

/**
 * 从 fundf10 markdown 里抽分红表格行。
 * 表格格式：| 2026年 | 2026-04-17 | 2026-04-20 | 每份派现金0.0050元 | 2026-04-23 |
 *           年份      权益登记日    除息日       每份分红金额          分红发放日
 *
 * @returns Array<{year, register_date, ex_date, amount, pay_date}>
 */
function parseDividendsFromMarkdown(md) {
  const lines = md.split('\n');
  const dividends = [];
  // 匹配表格行：5 列，含 "每份派现金X.XXXX元"
  const re = /^\|\s*(\d{4})年?\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*每份派现金(\d+\.\d+)元?\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|/;
  for (const line of lines) {
    const m = line.match(re);
    if (m) {
      dividends.push({
        year: parseInt(m[1]),
        register_date: m[2],
        ex_date: m[3],
        amount: parseFloat(m[4]),
        pay_date: m[5],
      });
    }
  }
  return dividends;
}

function ttmSum(dividends, asOf = new Date()) {
  const cutoff = new Date(asOf.getTime() - 365 * 86400000);
  return dividends
    .filter((d) => new Date(d.ex_date) >= cutoff && new Date(d.ex_date) <= asOf)
    .reduce((s, d) => s + d.amount, 0);
}

/**
 * 抓某只标的的分红记录。
 * @param {string} code
 * @param {Object} [opts]
 * @param {Date}   [opts.asOf=今天]
 * @returns {Promise<{
 *   code, source_url,
 *   dividends: Array,
 *   ttm_dividend: number|null,
 *   ttm_window: { from, to },
 *   note: string
 * }>}
 */
export async function fetchFundf10Dividends(code, opts = {}) {
  const asOf = opts.asOf || new Date();
  const url = `https://fundf10.eastmoney.com/fhsp_${code}.html`;
  const r = await fetchUrl(url, { maxChars: 30000 });

  if (r.error) {
    return {
      code,
      source_url: url,
      dividends: [],
      ttm_dividend: null,
      error: r.error,
      note: 'fundf10 fetch failed',
    };
  }

  const dividends = parseDividendsFromMarkdown(r.markdown);
  const ttm = ttmSum(dividends, asOf);
  const ttmFromDate = new Date(asOf.getTime() - 365 * 86400000);

  // 没找到任何分红，且页面明确写"暂无分红信息"
  const explicitNoDividend = r.markdown.includes('暂无分红信息');
  const note = dividends.length === 0
    ? (explicitNoDividend
       ? 'fundf10 显式标注"暂无分红信息"——历史无分红或页面尚未更新'
       : 'fundf10 未解析到表格行（可能页面改版或是新发标的）')
    : `从 fundf10 解析到 ${dividends.length} 条历史分红，过去 365 天 ${dividends.filter((d) => new Date(d.ex_date) >= ttmFromDate).length} 条`;

  return {
    code,
    source_url: url,
    dividends,
    ttm_dividend: dividends.length === 0 && explicitNoDividend ? 0 : Number(ttm.toFixed(4)),
    ttm_window: { from: ttmFromDate.toISOString().slice(0, 10), to: asOf.toISOString().slice(0, 10) },
    explicit_no_dividend: explicitNoDividend,
    note,
  };
}
