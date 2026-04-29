import type { CandidateInfo } from '@/lib/candidates';
import { describeFailure } from '@/lib/candidates';
import { categoryLabel, formatPercent, formatPrice } from '@/lib/format';

const SUBTYPE_LABEL: Record<string, string> = {
  consumption: '消费/商业',
  rental_housing: '保租房',
  energy: '能源基建',
  transportation: '交通',
  logistics: '物流',
  park: '园区',
  municipal: '市政环保',
};

export function CandidateCard({ candidate }: { candidate: CandidateInfo }) {
  const reasons = describeFailure(candidate);
  const subtype = candidate.reitSubtype
    ? SUBTYPE_LABEL[candidate.reitSubtype] ?? candidate.reitSubtype
    : null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-3 opacity-60 transition hover:opacity-90">
      <div className="flex items-baseline gap-2 text-xs">
        <span className="font-mono text-slate-500">{candidate.code}</span>
        <span className="font-medium text-slate-300">{candidate.name}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
        <span className="rounded bg-slate-800 px-1.5 py-0.5">
          {categoryLabel(candidate.category)}
        </span>
        {subtype && (
          <span className="rounded bg-slate-800 px-1.5 py-0.5">{subtype}</span>
        )}
        {candidate.listingYears != null && (
          <span>上市 {candidate.listingYears.toFixed(1)} 年</span>
        )}
        {candidate.aumYi != null && (
          <span>规模 {candidate.aumYi.toFixed(1)} 亿</span>
        )}
      </div>

      <div className="mt-2 grid grid-cols-3 gap-1 text-[11px]">
        <Mini label="TTM 分红" value={candidate.ttmDividend != null ? formatPrice(candidate.ttmDividend, 4) : '—'} />
        <Mini label="实时率" value={formatPercent(candidate.currentYieldPct, 2)} />
        <Mini label="筛选分" value={candidate.totalScore != null ? candidate.totalScore.toFixed(1) : '—'} />
      </div>

      <div className="mt-2 rounded bg-amber-500/5 px-2 py-1 text-[10px] text-amber-400/80 ring-1 ring-amber-500/15">
        <span className="font-bold">📋 候选原因</span>
        <ul className="mt-0.5">
          {reasons.map((r, i) => (
            <li key={i}>· {r}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-slate-800/40 px-1.5 py-0.5">
      <div className="text-[9px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className="font-mono text-slate-300">{value}</div>
    </div>
  );
}
