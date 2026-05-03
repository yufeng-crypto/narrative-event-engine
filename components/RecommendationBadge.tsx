import type { Recommendation, DataStatus } from '@/lib/types';

const TONE_STYLES = {
  success: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/40 border-emerald-500/40',
  warning: 'bg-amber-500/15 text-amber-300 ring-amber-500/40 border-amber-500/40',
  info: 'bg-sky-500/15 text-sky-300 ring-sky-500/40 border-sky-500/40',
  neutral: 'bg-slate-700/30 text-slate-300 ring-slate-600 border-slate-700',
  danger: 'bg-rose-500/15 text-rose-300 ring-rose-500/40 border-rose-500/40',
};

/** Hero 推荐区 — dashboard 上每张卡片最显眼的内容 */
export function RecommendationBox({
  recommendation,
  dataStatus,
}: {
  recommendation: Recommendation;
  dataStatus: DataStatus;
}) {
  const styles = TONE_STYLES[recommendation.tone];
  return (
    <div className={`rounded-lg border-2 px-4 py-3 ring-1 ${styles}`}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-base font-bold">{recommendation.label}</div>
        {dataStatus.complete ? (
          <span className="text-[10px] font-medium text-emerald-400/80">✅ 数据完整</span>
        ) : (
          <span className="text-[10px] font-medium text-amber-400/80">
            ⚠️ 缺 {dataStatus.missing.join('、')}
          </span>
        )}
      </div>
      <div className="mt-1 text-xs text-slate-300/90">{recommendation.reason}</div>
    </div>
  );
}
