import type { SignalLevel } from '@/lib/types';

const LABEL: Record<SignalLevel, string> = {
  hold: 'HOLD · 等',
  watch: 'WATCH · 观察',
  buy_now: 'BUY · 可建仓',
};

const STYLES: Record<SignalLevel, string> = {
  hold: 'bg-slate-700 text-slate-200 ring-slate-600',
  watch: 'bg-amber-500/20 text-amber-300 ring-amber-500/40',
  buy_now: 'bg-emerald-500/20 text-emerald-300 ring-emerald-500/40',
};

export function SignalBadge({ level }: { level: SignalLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-bold ring-1 ${STYLES[level]}`}
    >
      {LABEL[level]}
    </span>
  );
}
