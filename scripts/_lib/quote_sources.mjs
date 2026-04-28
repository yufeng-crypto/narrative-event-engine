/**
 * 多数据源行情聚合器：优先东方财富，失败回退腾讯财经。
 *
 * 当 push2.eastmoney.com 被限流/封禁时，腾讯 qt.gtimg.cn 是稳定的备选。
 * 两者返回的字段不同，本模块统一成 Quote 接口。
 */

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

/**
 * @typedef {Object} Quote
 * @property {string} code
 * @property {string} name
 * @property {number} price       当前价
 * @property {number} prevClose   昨收
 * @property {number} open
 * @property {number} high
 * @property {number} low
 * @property {number} changePct
 * @property {number|null} aum    总市值（元），可能为 null
 * @property {string} source      'eastmoney' | 'tencent'
 */

/** 东方财富 push2（首选） */
async function fetchFromEastMoney(code, market) {
  const secid = `${market === 'sh' ? '1' : '0'}.${code}`;
  const url =
    'https://push2.eastmoney.com/api/qt/stock/get?' +
    new URLSearchParams({
      secid,
      ut: 'fa5fd1943c7b386f172d6893dbfba10b',
      invt: '2',
      fltt: '2',
      fields: 'f43,f44,f45,f46,f57,f58,f60,f117,f168,f170',
    });
  const r = await fetch(url, {
    headers: {
      'User-Agent': UA,
      Accept: 'application/json',
      Referer: 'https://quote.eastmoney.com/',
    },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  if (!j?.data || j.data.f43 == null) throw new Error('empty');
  const d = j.data;
  return {
    code,
    name: d.f58 ?? '',
    price: d.f43,
    prevClose: d.f60,
    open: d.f46,
    high: d.f44,
    low: d.f45,
    changePct: d.f170,
    aum: d.f117 ?? null,
    source: 'eastmoney',
  };
}

/** 腾讯财经 qt.gtimg.cn（备选）*/
async function fetchFromTencent(code, market) {
  const symbol = `${market}${code}`;
  const url = `https://qt.gtimg.cn/q=${symbol}`;
  const r = await fetch(url, {
    headers: {
      'User-Agent': UA,
      Accept: 'text/plain',
      Referer: 'https://gu.qq.com/',
    },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  // 腾讯返回 GBK 编码的 JS 变量赋值，需要按 latin1 读再 GBK 解
  const buf = await r.arrayBuffer();
  // 使用 TextDecoder 处理 GBK
  const text = new TextDecoder('gbk').decode(buf);
  const m = text.match(/=\s*"([^"]+)"/);
  if (!m) throw new Error('parse error');
  const parts = m[1].split('~');
  if (parts.length < 50) throw new Error('not enough fields');
  // 腾讯 ETF/REIT 字段位置
  // 1: name, 2: code, 3: price, 4: prevClose, 5: open, 6: 成交量(手),
  // 30: 涨跌, 31: 涨跌幅%, 33: 最高, 34: 最低
  // 总市值在 45 (浮动总市值) 或 46 (流通市值)
  const f = (i) => parts[i];
  const num = (i) => parseFloat(parts[i]);
  return {
    code,
    name: f(1),
    price: num(3),
    prevClose: num(4),
    open: num(5),
    high: num(33),
    low: num(34),
    changePct: num(32),
    aum: parts[45] ? parseFloat(parts[45]) * 1e8 : null, // 单位是亿
    source: 'tencent',
  };
}

/**
 * 主入口：先 EastMoney → 失败回退 Tencent。
 * 任一成功即返回。两个都失败抛异常。
 */
export async function fetchQuote(code, market, { retry = 2 } = {}) {
  const sources = [
    { name: 'eastmoney', fn: fetchFromEastMoney },
    { name: 'tencent', fn: fetchFromTencent },
  ];
  let lastErr;
  for (const s of sources) {
    for (let i = 0; i < retry; i++) {
      try {
        return await s.fn(code, market);
      } catch (e) {
        lastErr = new Error(`${s.name}: ${e.message}`);
        if (i < retry - 1) {
          await new Promise((r) => setTimeout(r, 500 * (i + 1)));
        }
      }
    }
  }
  throw lastErr ?? new Error('all sources failed');
}

// ============================================================
// 历史 K 线（多源 fallback）
// ============================================================

/** 东方财富 push2his */
async function fetchKlineFromEastMoney(code, market, { beg = '20210101', limit = 5000 } = {}) {
  const secid = `${market === 'sh' ? '1' : '0'}.${code}`;
  const url =
    'https://push2his.eastmoney.com/api/qt/stock/kline/get?' +
    new URLSearchParams({
      secid,
      ut: 'fa5fd1943c7b386f172d6893dbfba10b',
      fields1: 'f1,f2,f3,f4,f5',
      fields2: 'f51,f52,f53,f54,f55,f56,f57,f58,f59',
      klt: '101',
      fqt: '1',
      beg,
      end: '20990101',
      lmt: String(limit),
    });
  const r = await fetch(url, {
    headers: { 'User-Agent': UA, Referer: 'https://quote.eastmoney.com/' },
    signal: AbortSignal.timeout(10000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  const klines = j?.data?.klines ?? [];
  if (klines.length === 0) throw new Error('empty klines');
  return klines.map((line) => {
    const [date, open, close, high, low, volume, amount, changePct] = line.split(',');
    return {
      date,
      open: parseFloat(open),
      close: parseFloat(close),
      high: parseFloat(high),
      low: parseFloat(low),
      volume: parseFloat(volume),
      amount: parseFloat(amount),
      changePct: parseFloat(changePct) || 0,
    };
  });
}

/** 腾讯财经 web.ifzq.gtimg.cn fqkline */
async function fetchKlineFromTencent(code, market, { limit = 5000 } = {}) {
  const symbol = `${market}${code}`;
  // qfq = 前复权
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${symbol},day,,,${limit},qfq`;
  const r = await fetch(url, {
    headers: { 'User-Agent': UA, Referer: 'https://gu.qq.com/' },
    signal: AbortSignal.timeout(10000),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  // 数据路径: data.{symbol}.day（前复权）或 qfqday
  const sect = j?.data?.[symbol];
  const arr = sect?.qfqday ?? sect?.day ?? [];
  if (arr.length === 0) throw new Error('empty klines');
  return arr.map((line) => ({
    date: line[0],
    open: parseFloat(line[1]),
    close: parseFloat(line[2]),
    high: parseFloat(line[3]),
    low: parseFloat(line[4]),
    volume: parseFloat(line[5]),
    amount: 0, // tencent doesn't return amount in this endpoint
    changePct: 0,
  }));
}

/**
 * 取历史日线（多源 fallback）
 *
 * @returns {Promise<Array<{date,open,close,high,low,volume,amount,changePct}>>}
 */
export async function fetchKline(code, market, opts = {}) {
  const sources = [
    { name: 'eastmoney', fn: fetchKlineFromEastMoney },
    { name: 'tencent', fn: fetchKlineFromTencent },
  ];
  const retry = opts.retry ?? 2;
  let lastErr;
  for (const s of sources) {
    for (let i = 0; i < retry; i++) {
      try {
        return await s.fn(code, market, opts);
      } catch (e) {
        lastErr = new Error(`${s.name}: ${e.message}`);
        if (i < retry - 1) {
          await new Promise((r) => setTimeout(r, 500 * (i + 1)));
        }
      }
    }
  }
  throw lastErr ?? new Error('all kline sources failed');
}
