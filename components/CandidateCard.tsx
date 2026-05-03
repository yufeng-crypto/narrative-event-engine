import type { CandidateInfo } from '@/lib/candidates';

const SUBTYPE_LABEL: Record<string, string> = {
  consumption: '消费',
  rental_housing: '保租房',
  energy: '能源',
  transportation: '交通',
  logistics: '物流',
  park: '园区',
  municipal: '市政',
};

/** 极简候选标的卡片 — 一行展示，不强调风险（候选池本来就不入仓）*/
export function CandidateCard({ candidate }: { candidate: CandidateInfo }) {
  const subtype = candidate.reitSubtype
    ? SUBTYPE_LABEL[candidate.reitSubtype] ?? candidate.reitSubtype
    : null;

  return (
    <div className="rounded-md border border-slate-800/70 bg-slate-900/30 px-3 py-2 opacity-65 transition hover:opacity-95">
      <div className="flex items-baseline gap-2 text-xs">
        <span className="font-mono text-slate-500">{candidate.code}</span>
        <span className="flex-1 truncate font-medium text-slate-300">
          {candidate.name}
        </span>
        {subtype && (
          <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">
            {subtype}
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-3 text-[10px] text-slate-500">
        {candidate.listingYears != null && (
          <span>上市 {candidate.listingYears.toFixed(1)} 年</span>
        )}
        {candidate.aumYi != null && (
          <span>规模 {candidate.aumYi.toFixed(1)} 亿</span>
        )}
        {candidate.currentYieldPct != null && (
          <span>分派率 {candidate.currentYieldPct.toFixed(2)}%</span>
        )}
      </div>
    </div>
  );
}
