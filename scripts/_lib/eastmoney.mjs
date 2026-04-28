/**
 * 东方财富数据接口 — 脚本端使用版本。
 *
 * 与 lib/eastmoney.ts 不同：脚本里我们要拉全市场列表 / 历史数据，所以接入更多 endpoint。
 */

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

const HEADERS = {
  'User-Agent': UA,
  Accept: 'application/json, text/plain, */*',
  Referer: 'https://quote.eastmoney.com/',
};

/** 拉全市场 ETF 列表（包括红利、宽基、行业等） */
export async function fetchAllEtfs() {
  // fs=b:MK0021 是 ETF 板块筛选条件
  const url =
    'https://push2.eastmoney.com/api/qt/clist/get?' +
    new URLSearchParams({
      pn: '1',
      pz: '500',
      po: '1',
      np: '1',
      ut: 'bd1d9ddb04089700cf9c27f6f7426281',
      fltt: '2',
      invt: '2',
      fid: 'f3',
      fs: 'b:MK0021',
      fields: 'f2,f3,f4,f12,f13,f14,f17,f18,f20,f21,f24,f25,f152',
    });
  return fetchClist(url);
}

/** 拉全市场 REITs 列表 */
export async function fetchAllReits() {
  const url =
    'https://push2.eastmoney.com/api/qt/clist/get?' +
    new URLSearchParams({
      pn: '1',
      pz: '200',
      po: '1',
      np: '1',
      ut: 'bd1d9ddb04089700cf9c27f6f7426281',
      fltt: '2',
      invt: '2',
      fid: 'f3',
      fs: 'b:MK0827',
      fields: 'f2,f3,f4,f12,f13,f14,f17,f18,f20,f21,f24,f25,f152',
    });
  return fetchClist(url);
}

async function fetchClist(url) {
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  const rows = json?.data?.diff ?? [];
  return rows.map((r) => ({
    code: r.f12,
    name: r.f14,
    market: r.f13 === 1 ? 'sh' : 'sz', // 1=sh, 0=sz
    price: r.f2,
    changePct: r.f3,
    changeAmt: r.f4,
    high: r.f17,
    low: r.f18,
    aum: r.f20, // 总市值（元）
    aumCirc: r.f21, // 流通市值（元）
    open: r.f24,
    prevClose: r.f25,
  }));
}

/**
 * 拉历史日线（push2his.kline）
 *
 * @param {string} secid - "1.515100" 或 "0.180601" 格式
 * @param {number} klt - K线类型: 101=日线, 102=周线, 103=月线
 * @param {number} fqt - 复权: 0=不复权, 1=前复权, 2=后复权
 * @param {string} beg - 开始日期 yyyymmdd
 * @param {string} end - 结束日期
 */
export async function fetchKline(secid, { klt = 101, fqt = 1, beg = '20210101', end = '20990101' } = {}) {
  const url =
    'https://push2his.eastmoney.com/api/qt/stock/kline/get?' +
    new URLSearchParams({
      secid,
      ut: 'fa5fd1943c7b386f172d6893dbfba10b',
      fields1: 'f1,f2,f3,f4,f5',
      fields2: 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
      klt: String(klt),
      fqt: String(fqt),
      beg,
      end,
      lmt: '5000',
    });
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`kline HTTP ${res.status}`);
  const json = await res.json();
  const klines = json?.data?.klines ?? [];
  return klines.map((line) => {
    // 格式: "2026-04-28,1.443,1.451,1.452,1.442,xxx,xxx,涨跌幅,涨跌额,xxx,xxx"
    const [date, open, close, high, low, volume, amount, changePct] = line.split(',');
    return {
      date,
      open: parseFloat(open),
      close: parseFloat(close),
      high: parseFloat(high),
      low: parseFloat(low),
      volume: parseFloat(volume),
      amount: parseFloat(amount),
      changePct: parseFloat(changePct),
    };
  });
}

/**
 * 拉基金分红记录（fundf10）— 返回 HTML，需要正则解析
 *
 * 简化版：先用 API，如果不可靠再去爬 HTML
 */
export async function fetchDividendHistory(code) {
  // 用东方财富的 api.fund.eastmoney.com
  const url = `https://api.fund.eastmoney.com/F10/lsfh/?fundCode=${code}&pageIndex=1&pageSize=50`;
  const res = await fetch(url, {
    headers: {
      ...HEADERS,
      Referer: `https://fundf10.eastmoney.com/fhsp_${code}.html`,
    },
  });
  if (!res.ok) return [];
  const json = await res.json().catch(() => null);
  const rows = json?.Data?.LSFHList ?? [];
  return rows.map((r) => ({
    announceDate: r.FHGGRQ, // 公告日期
    rightDate: r.QXDJR, // 权益登记日
    exDate: r.CXRQ, // 除息日
    payDate: r.FHFFRQ, // 派发日期
    fhsl: parseFloat(r.FHFCBZ?.replace(/[^0-9.]/g, '') || '0') || 0, // 分红金额（元/份）
    raw: r,
  }));
}

/** secid 拼接 */
export function buildSecId(code, market) {
  return `${market === 'sh' ? '1' : '0'}.${code}`;
}
