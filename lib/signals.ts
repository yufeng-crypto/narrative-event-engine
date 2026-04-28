import type { ProductConfig, Quote, SignalLevel, SignalResult } from './types';

/**
 * 计算实时信号：基于配置的阈值 + 实时报价。
 * 双触发：股息率/分派率 OR 价格阈值，任一命中升级一档。
 */
export function evaluateSignal(
  cfg: ProductConfig,
  quote: Quote,
): SignalResult {
  const triggers: string[] = [];
  let level: SignalLevel = 'hold';

  if (quote.price == null || quote.price <= 0) {
    return {
      level: 'hold',
      ttmYield: null,
      premiumPct: null,
      triggers: ['无实时价格'],
    };
  }

  const ttmYield = (cfg.ttmDividend / quote.price) * 100;
  const premiumPct =
    cfg.navRefPrice != null
      ? ((quote.price - cfg.navRefPrice) / cfg.navRefPrice) * 100
      : null;

  // 股息率/分派率触发
  if (ttmYield >= cfg.buyYield) {
    level = 'buy_now';
    triggers.push(`实时分派率 ${ttmYield.toFixed(2)}% ≥ buy 阈值 ${cfg.buyYield}%`);
  } else if (ttmYield >= cfg.watchYield) {
    level = 'watch';
    triggers.push(`实时分派率 ${ttmYield.toFixed(2)}% ≥ watch 阈值 ${cfg.watchYield}%`);
  }

  // 价格触发（REITs 用得上）
  if (cfg.buyPrice != null && quote.price <= cfg.buyPrice) {
    level = 'buy_now';
    triggers.push(`价格 ${quote.price.toFixed(3)} ≤ buy 阈值 ${cfg.buyPrice}`);
  } else if (cfg.watchPrice != null && quote.price <= cfg.watchPrice && level === 'hold') {
    level = 'watch';
    triggers.push(`价格 ${quote.price.toFixed(3)} ≤ watch 阈值 ${cfg.watchPrice}`);
  }

  // 高溢价警告（不影响 level，只是提示）
  if (premiumPct != null && premiumPct >= 30) {
    triggers.push(`⚠️ 溢价 ${premiumPct.toFixed(1)}%（贵）`);
  }

  if (level === 'hold' && triggers.length === 0) {
    triggers.push(
      `分派率 ${ttmYield.toFixed(2)}% < watch 阈值 ${cfg.watchYield}% — 等更便宜`,
    );
  }

  return { level, ttmYield, premiumPct, triggers };
}
