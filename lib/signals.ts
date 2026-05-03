import type {
  DataStatus,
  ProductConfig,
  Quote,
  Recommendation,
  SignalLevel,
  SignalResult,
} from './types';

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

/**
 * 综合建议：合成 tier + grade + signal + redFlags 给一个明确的"该怎么办"。
 * 这是 dashboard 给用户看的唯一决策字段。
 */
export function deriveRecommendation(
  cfg: ProductConfig,
  signal: SignalResult,
  dataStatus: DataStatus,
): Recommendation {
  // 1. 数据不完整 → 不能给明确建议
  if (!dataStatus.complete) {
    return {
      action: 'no_action',
      label: '⏸ 数据不全',
      tone: 'neutral',
      reason: `缺：${dataStatus.missing.join('、')}。补齐后才能给建议`,
    };
  }

  // 2. C / C+ / D 级 → 建议剔除（无论价格信号）
  if (cfg.grade === 'C' || cfg.grade === 'C+' || cfg.grade === 'D') {
    return {
      action: 'avoid',
      label: '🚫 建议剔除',
      tone: 'danger',
      reason: '基本面有结构性问题，分派率高反映市场已 price-in，不建议入仓',
    };
  }

  // 3. 价格触发 BUY
  if (signal.level === 'buy_now') {
    if (cfg.tier === 'core' && (cfg.grade === 'A+' || cfg.grade === 'A')) {
      return {
        action: 'buy_now',
        label: '🟢 立即建仓',
        tone: 'success',
        reason: '核心资产 + 价格已触发，可分批入场',
      };
    }
    if (cfg.tier === 'supporting') {
      return {
        action: 'small_test',
        label: '🟢 可建仓（小仓）',
        tone: 'success',
        reason: '辅助资产 + 价格已触发，建议单只仓位 ≤ 30 万',
      };
    }
    // tier=watch + BUY 价格信号 → 仍建议小仓
    return {
      action: 'small_test',
      label: '🟡 谨慎试水',
      tone: 'warning',
      reason: '价格触发但仅 watch tier，建议小仓位（≤ 10 万）观察',
    };
  }

  // 4. WATCH 信号
  if (signal.level === 'watch') {
    if (cfg.grade === 'A+' || cfg.grade === 'A' || cfg.grade === 'A-') {
      return {
        action: 'watch_active',
        label: '🔵 持仓观察',
        tone: 'info',
        reason: '接近 BUY 阈值，分派率/价格已进入观察区',
      };
    }
    return {
      action: 'no_action',
      label: '⏸ 暂不建仓',
      tone: 'neutral',
      reason: '虽接近触发但基本面一般，等更明确机会',
    };
  }

  // 5. HOLD 信号（价格不便宜）
  if (cfg.tier === 'core' && (cfg.grade === 'A+' || cfg.grade === 'A')) {
    return {
      action: 'wait_pullback',
      label: '⏳ 等待回调',
      tone: 'info',
      reason: '资产优质但当前价格偏贵，等回调到 buy 阈值再入场',
    };
  }
  return {
    action: 'no_action',
    label: '⏸ 暂不建仓',
    tone: 'neutral',
    reason: '价格不到位且无显著优势',
  };
}

/**
 * 检查决策所需数据是否完整。返回 missing 字段告诉用户缺什么。
 */
export function checkDataCompleteness(
  cfg: ProductConfig,
  quote: Quote,
): DataStatus {
  const missing: string[] = [];
  if (cfg.ttmDividend == null || cfg.ttmDividend === 0) {
    missing.push('TTM 分红');
  }
  if (cfg.qualityScore == null) {
    missing.push('Stage 4 评估');
  }
  if (quote.source === 'error' || quote.price == null) {
    missing.push('实时报价');
  }
  // 评估时效性
  if (cfg.ttmDividendAsOf) {
    const days = Math.floor(
      (Date.now() - new Date(cfg.ttmDividendAsOf).getTime()) / 86400000,
    );
    if (days > 180) {
      missing.push(`数据 ${days} 天前（>6月）`);
    }
  }
  return { complete: missing.length === 0, missing };
}
