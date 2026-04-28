import { categoryLabel, formatPercent, formatPrice } from '@/lib/format';
import type { ProductView } from '@/lib/types';
import { SignalBadge } from './SignalBadge';
import { GradeBadge, TierBadge } from './TierBadge';

const CARD_BORDER: Record<string, string> = {
  hold: 'border-slate-700',
  watch: 'border-amber-500/60',
  buy_now: 'border-emerald-500/60',
};

const TIER_OUTLINE: Record<string, string> = {
  core: 'ring-2 ring-amber-500/40',
  supporting: 'ring-1 ring-slate-700',
  watch: 'ring-1 ring-slate-800 opacity-90',
};

export function ProductCard({ view }: { view: ProductView }) {
  const { config, quote, signal } = view;

  return (
    <div
      className={`rounded-2xl border bg-slate-900/60 p-5 shadow-lg backdrop-blur ${CARD_BORDER[signal.level]} ${TIER_OUTLINE[config.tier]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-xs">
            <TierBadge tier={config.tier} />
            <GradeBadge grade={config.grade} score={config.qualityScore} />
            <span className="text-slate-500">·</span>
            <span className="font-medium uppercase tracking-wider text-slate-400">
              {categoryLabel(config.category)}
            </span>
            <span className="font-mono text-slate-500">{config.code}</span>
          </div>
          <div className="mt-1.5 text-lg font-semibold text-slate-100">
            {config.shortName}
          </div>
          <div className="text-xs text-slate-500">{config.name}</div>
        </div>
        <SignalBadge level={signal.level} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
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
        <Stat label="昨收" value={formatPrice(quote.prevClose)} mono dim />
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
        <Stat
          label="watch / buy"
          value={`${config.watchYield}% / ${config.buyYield}%`}
          dim
        />
        {config.navRefPrice != null && (
          <Stat
            label={`溢价 (NAV ${config.navRefPrice})`}
            value={formatPercent(signal.premiumPct)}
            mono
            tone={
              signal.premiumPct == null
                ? 'neutral'
                : signal.premiumPct >= 30
                  ? 'down'
                  : signal.premiumPct >= 10
                    ? 'warn'
                    : 'up'
            }
          />
        )}
      </div>

      {signal.triggers.length > 0 && (
        <ul className="mt-4 space-y-1 text-xs text-slate-400">
          {signal.triggers.map((t, i) => (
            <li key={i}>· {t}</li>
          ))}
        </ul>
      )}

      {config.redFlags && config.redFlags.length > 0 && (
        <div className="mt-3 rounded-lg bg-rose-500/5 px-3 py-2 ring-1 ring-rose-500/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-rose-400">
            ⚠️ Red Flags
          </div>
          <ul className="mt-1 space-y-0.5 text-xs text-rose-300/90">
            {config.redFlags.map((f, i) => (
              <li key={i}>· {f}</li>
            ))}
          </ul>
        </div>
      )}

      {config.tierReason && (
        <div className="mt-2 text-[11px] italic text-slate-500">
          📋 {config.tierReason}
        </div>
      )}

      <div className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
        <div>
          TTM 分红 <span className="font-mono">{config.ttmDividend}</span> 元/份（更新于 {config.ttmDividendAsOf}）
        </div>
        {config.notes && <div className="mt-1">{config.notes}</div>}
        {quote.error && (
          <div className="mt-1 text-rose-400">⚠️ 行情异常: {quote.error}</div>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  mono,
  dim,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  mono?: boolean;
  dim?: boolean;
  tone?: 'neutral' | 'up' | 'down' | 'warn';
}) {
  const toneClass = {
    neutral: 'text-slate-200',
    up: 'text-emerald-400',
    down: 'text-rose-400',
    warn: 'text-amber-400',
  }[tone];

  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div
        className={`${mono ? 'font-mono' : ''} ${dim ? 'text-slate-400' : toneClass} text-base font-semibold`}
      >
        {value}
      </div>
    </div>
  );
}
