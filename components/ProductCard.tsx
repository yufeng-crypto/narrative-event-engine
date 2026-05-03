import { categoryLabel, formatPercent, formatPrice } from '@/lib/format';
import type { ProductView } from '@/lib/types';
import { RecommendationBox } from './RecommendationBadge';
import { GradeBadge, TierBadge } from './TierBadge';

const TONE_BORDER = {
  success: 'border-emerald-500/40',
  warning: 'border-amber-500/40',
  info: 'border-sky-500/40',
  neutral: 'border-slate-700',
  danger: 'border-rose-500/40',
};

/**
 * 决策驱动卡片：
 *   - Hero 区：综合建议 + 数据完整度
 *   - 实时数据：价格 / 涨跌 / 分派率
 *   - 关键风险（仅 top 3 致命/警示）
 *   - 详情可展开（详细 red flags / 阈值 / tier 理由 / 评估元数据）
 */
export function ProductCard({ view }: { view: ProductView }) {
  const { config, quote, signal, recommendation, dataStatus } = view;
  const borderClass = TONE_BORDER[recommendation.tone];

  // 致命红旗优先（🔴/🚨开头），其余警示放详情
  const allFlags = config.redFlags ?? [];
  const criticalFlags = allFlags.filter(
    (f) => f.startsWith('🔴') || f.startsWith('🚨'),
  );
  const warningFlags = allFlags.filter(
    (f) => f.startsWith('⚠️') && !criticalFlags.includes(f),
  );
  const otherFlags = allFlags.filter(
    (f) => !criticalFlags.includes(f) && !warningFlags.includes(f),
  );
  const heroFlags = [...criticalFlags, ...warningFlags].slice(0, 3);
  const detailFlags = allFlags.filter((f) => !heroFlags.includes(f));

  return (
    <div
      className={`rounded-2xl border-2 bg-slate-900/60 p-5 shadow-lg backdrop-blur ${borderClass}`}
    >
      {/* Header: code + name + tier/grade */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-mono text-slate-500">{config.code}</span>
            <span className="font-medium text-slate-400">
              {categoryLabel(config.category)}
            </span>
          </div>
          <div className="mt-0.5 text-base font-semibold text-slate-100">
            {config.shortName}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <TierBadge tier={config.tier} />
          <GradeBadge grade={config.grade} score={config.qualityScore} />
        </div>
      </div>

      {/* 实时数据 - 紧凑一行 */}
      <div className="mt-3 flex items-baseline gap-4 rounded-lg bg-slate-800/40 px-3 py-2 text-sm">
        <Stat label="实时价" value={formatPrice(quote.price)} mono />
        <Stat
          label="涨跌"
          value={formatPercent(quote.changePct)}
          mono
          tone={
            quote.changePct == null
              ? 'neutral'
              : quote.changePct > 0
                ? 'up'
                : quote.changePct < 0
                  ? 'down'
                  : 'neutral'
          }
        />
        <Stat
          label="实时分派率"
          value={formatPercent(signal.ttmYield)}
          mono
          tone={
            signal.ttmYield == null
              ? 'neutral'
              : signal.ttmYield >= config.buyYield
                ? 'up'
                : signal.ttmYield >= config.watchYield
                  ? 'warn'
                  : 'down'
          }
        />
      </div>

      {/* HERO: 综合建议 */}
      <div className="mt-4">
        <RecommendationBox
          recommendation={recommendation}
          dataStatus={dataStatus}
        />
      </div>

      {/* Top 关键风险（仅 top 3） */}
      {heroFlags.length > 0 && (
        <div className="mt-3 rounded-lg bg-rose-500/5 px-3 py-2 ring-1 ring-rose-500/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-rose-400">
            关键风险
          </div>
          <ul className="mt-1 space-y-0.5 text-xs text-rose-300/90">
            {heroFlags.map((f, i) => (
              <li key={i}>· {f}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 详情可展开（默认折叠） */}
      <details className="mt-3 group">
        <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-300 select-none list-none flex items-center gap-1">
          <span className="transition group-open:rotate-90">▶</span>
          详情（阈值 / 全部风险 / 资产说明）
        </summary>
        <div className="mt-2 space-y-2 border-l-2 border-slate-800 pl-3 text-[11px] text-slate-400">
          <div>
            <strong className="text-slate-300">买入阈值：</strong>
            分派率 ≥ {config.watchYield}% 进观察 / ≥ {config.buyYield}% 可建仓
            {config.buyPrice != null && ` · 价格 ≤ ${config.buyPrice} 元可建仓`}
          </div>
          {detailFlags.length > 0 && (
            <div>
              <strong className="text-slate-300">其他风险：</strong>
              <ul className="mt-1 space-y-0.5">
                {detailFlags.map((f, i) => (
                  <li key={i}>· {f}</li>
                ))}
              </ul>
            </div>
          )}
          {config.tierReason && (
            <div>
              <strong className="text-slate-300">分级原因：</strong>{' '}
              {config.tierReason}
            </div>
          )}
          <div>
            <strong className="text-slate-300">底层资产：</strong>{' '}
            {config.notes ?? '—'}
          </div>
          <div>
            <strong className="text-slate-300">TTM 分红：</strong>
            <span className="font-mono">{config.ttmDividend}</span> 元/份（更新于{' '}
            {config.ttmDividendAsOf}）
          </div>
          {quote.error && (
            <div className="text-rose-400">
              ⚠️ 行情异常：{quote.error}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: 'neutral' | 'up' | 'down' | 'warn';
}) {
  const toneClass = {
    neutral: 'text-slate-200',
    up: 'text-emerald-400',
    down: 'text-rose-400',
    warn: 'text-amber-400',
  }[tone];

  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span className={`${mono ? 'font-mono' : ''} ${toneClass} font-semibold`}>
        {value}
      </span>
    </div>
  );
}
