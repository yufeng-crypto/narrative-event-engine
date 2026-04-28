import type { Market, Quote } from './types';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

interface PartialQuote {
  name: string;
  price: number;
  prevClose: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  changePct: number | null;
}

/** 东方财富 push2（首选） */
async function fetchFromEastMoney(
  code: string,
  market: Market,
): Promise<PartialQuote> {
  const secid = `${market === 'sh' ? '1' : '0'}.${code}`;
  const params = new URLSearchParams({
    secid,
    ut: 'fa5fd1943c7b386f172d6893dbfba10b',
    invt: '2',
    fltt: '2',
    fields: 'f43,f44,f45,f46,f57,f58,f60,f170',
  });
  const res = await fetch(
    `https://push2.eastmoney.com/api/qt/stock/get?${params.toString()}`,
    {
      headers: {
        'User-Agent': UA,
        Accept: 'application/json',
        Referer: 'https://quote.eastmoney.com/',
      },
      next: { revalidate: 60, tags: [`quote:${code}`] },
      signal: AbortSignal.timeout(8000),
    },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const j = (await res.json()) as {
    data?: {
      f43?: number;
      f44?: number;
      f45?: number;
      f46?: number;
      f58?: string;
      f60?: number;
      f170?: number;
    };
  };
  if (j?.data?.f43 == null) throw new Error('empty');
  const d = j.data;
  const price = d.f43;
  if (price == null) throw new Error('no price');
  return {
    name: d.f58 ?? '',
    price,
    prevClose: d.f60 ?? null,
    open: d.f46 ?? null,
    high: d.f44 ?? null,
    low: d.f45 ?? null,
    changePct: d.f170 ?? null,
  };
}

/** 腾讯财经 qt.gtimg.cn（备选）— GBK 编码，需手动解码 */
async function fetchFromTencent(
  code: string,
  market: Market,
): Promise<PartialQuote> {
  const symbol = `${market}${code}`;
  const res = await fetch(`https://qt.gtimg.cn/q=${symbol}`, {
    headers: {
      'User-Agent': UA,
      Referer: 'https://gu.qq.com/',
    },
    next: { revalidate: 60, tags: [`quote:${code}`] },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  const text = new TextDecoder('gbk').decode(buf);
  const m = text.match(/=\s*"([^"]+)"/);
  if (!m) throw new Error('parse error');
  const parts = m[1].split('~');
  if (parts.length < 50) throw new Error('not enough fields');
  const num = (i: number) => {
    const v = parseFloat(parts[i]);
    return Number.isFinite(v) ? v : null;
  };
  const price = num(3);
  if (price == null) throw new Error('no price');
  return {
    name: parts[1] ?? '',
    price,
    prevClose: num(4),
    open: num(5),
    high: num(33),
    low: num(34),
    changePct: num(32),
  };
}

/**
 * 取实时报价：先东方财富 → 失败回退腾讯。
 * 任一成功即返回。两个都失败返回 source='error' 的 Quote。
 */
export async function fetchEastMoneyQuote(
  code: string,
  market: Market,
): Promise<Quote> {
  const sources: { name: 'eastmoney' | 'tencent'; fn: typeof fetchFromEastMoney }[] = [
    { name: 'eastmoney', fn: fetchFromEastMoney },
    { name: 'tencent', fn: fetchFromTencent },
  ];

  let lastErr = '';
  for (const s of sources) {
    try {
      const p = await s.fn(code, market);
      return {
        code,
        name: p.name,
        price: p.price,
        prevClose: p.prevClose,
        open: p.open,
        high: p.high,
        low: p.low,
        changePct: p.changePct,
        fetchedAt: new Date().toISOString(),
        source: s.name,
      };
    } catch (e) {
      lastErr = `${s.name}: ${e instanceof Error ? e.message : 'unknown'}`;
    }
  }

  return {
    code,
    name: null,
    price: null,
    prevClose: null,
    open: null,
    high: null,
    low: null,
    changePct: null,
    fetchedAt: new Date().toISOString(),
    source: 'error',
    error: lastErr,
  };
}
