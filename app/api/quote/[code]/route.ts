import { NextResponse } from 'next/server';
import { fetchEastMoneyQuote } from '@/lib/eastmoney';
import { findProduct } from '@/lib/products';
import { evaluateSignal } from '@/lib/signals';

/**
 * GET /api/quote/[code]
 *
 * 调试用：返回某个监控池标的的实时报价 + 信号评估。
 * 仅对 PRODUCTS 池里登记过的代码生效。
 */
export async function GET(
  _req: Request,
  { params }: { params: { code: string } },
) {
  const cfg = findProduct(params.code);
  if (!cfg) {
    return NextResponse.json(
      { error: `code ${params.code} not in monitored pool` },
      { status: 404 },
    );
  }

  const quote = await fetchEastMoneyQuote(cfg.code, cfg.market);
  const signal = evaluateSignal(cfg, quote);

  return NextResponse.json({ config: cfg, quote, signal });
}
