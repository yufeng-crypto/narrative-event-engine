import type { Tier, Grade } from '@/lib/types';

const TIER_LABEL: Record<Tier, string> = {
  core: '🥇 核心',
  supporting: '🥈 辅助',
  watch: '🥉 监控',
};

const TIER_STYLES: Record<Tier, string> = {
  core: 'bg-gradient-to-r from-yellow-500/20 to-amber-500/20 text-amber-300 ring-amber-500/40',
  supporting: 'bg-slate-700/40 text-slate-300 ring-slate-600',
  watch: 'bg-slate-800/40 text-slate-500 ring-slate-700',
};

const GRADE_STYLES: Record<Grade, string> = {
  'A+': 'bg-emerald-500/30 text-emerald-300',
  A: 'bg-emerald-500/15 text-emerald-400',
  'A-': 'bg-emerald-500/10 text-emerald-500',
  'B+': 'bg-amber-500/15 text-amber-400',
  B: 'bg-amber-500/15 text-amber-500',
  'B-': 'bg-amber-500/10 text-amber-600',
  'C+': 'bg-rose-500/10 text-rose-500',
  C: 'bg-rose-500/15 text-rose-400',
  D: 'bg-rose-500/30 text-rose-300',
};

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${TIER_STYLES[tier]}`}
    >
      {TIER_LABEL[tier]}
    </span>
  );
}

export function GradeBadge({ grade, score }: { grade: Grade; score?: number }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-bold ${GRADE_STYLES[grade]}`}
    >
      {grade}
      {score != null && <span className="font-mono opacity-70">{score}</span>}
    </span>
  );
}
