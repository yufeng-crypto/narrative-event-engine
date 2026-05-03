import { CandidateCard } from '@/components/CandidateCard';
import { ProductCard } from '@/components/ProductCard';
import { RefreshButton } from '@/components/RefreshButton';
import {
  BUCKET_META,
  groupCandidates,
  loadCandidates,
  type CandidateBucket,
} from '@/lib/candidates';
import { fetchEastMoneyQuote } from '@/lib/eastmoney';
import { formatBjTime } from '@/lib/format';
import { PRODUCTS } from '@/lib/products';
import {
  checkDataCompleteness,
  deriveRecommendation,
  evaluateSignal,
} from '@/lib/signals';
import type { ProductView, Tier } from '@/lib/types';

export const dynamic = 'force-dynamic';

const TIER_TITLES: Record<Tier, { title: string; subtitle: string }> = {
  core: {
    title: '🥇 核心持仓池',
    subtitle: '可优先建仓 — 长期看好 + 政策支持',
  },
  supporting: {
    title: '🥈 辅助持仓池',
    subtitle: '合格资产 — 有 caveat 但可入仓',
  },
  watch: {
    title: '🥉 监控池',
    subtitle: '暂不入仓 — 等条件改善 / 与核心重叠 / 已发现风险',
  },
};

// 候选池分组按优先级展示顺序
const BUCKET_ORDER: CandidateBucket[] = [
  'missing_ttm_etf',
  'industry_squeeze',
  'newly_listed',
  'low_yield',
  'small_aum',
  'other',
];

async function loadView(): Promise<{ views: ProductView[]; ts: string }> {
  const views = await Promise.all(
    PRODUCTS.map(async (config) => {
      const quote = await fetchEastMoneyQuote(config.code, config.market);
      const signal = evaluateSignal(config, quote);
      const dataStatus = checkDataCompleteness(config, quote);
      const recommendation = deriveRecommendation(config, signal, dataStatus);
      return { config, quote, signal, recommendation, dataStatus };
    }),
  );
  return { views, ts: new Date().toISOString() };
}

// 综合建议在 tier 内的排序权重
const ACTION_ORDER: Record<string, number> = {
  buy_now: 0,
  small_test: 1,
  watch_active: 2,
  wait_pullback: 3,
  no_action: 4,
  avoid: 5,
};

export default async function HomePage() {
  const { views, ts } = await loadView();
  const candidates = loadCandidates();
  const grouped: Record<Tier, ProductView[]> = {
    core: [],
    supporting: [],
    watch: [],
  };
  for (const v of views) {
    grouped[v.config.tier].push(v);
  }
  for (const tier of Object.keys(grouped) as Tier[]) {
    grouped[tier].sort((a, b) => {
      const ra =
        ACTION_ORDER[a.recommendation.action] ?? 99;
      const rb =
        ACTION_ORDER[b.recommendation.action] ?? 99;
      if (ra !== rb) return ra - rb;
      return (b.config.qualityScore ?? 0) - (a.config.qualityScore ?? 0);
    });
  }

  // 各动作 count 统计（用于 header）
  const actionCounts = views.reduce<Record<string, number>>((acc, v) => {
    acc[v.recommendation.action] = (acc[v.recommendation.action] ?? 0) + 1;
    return acc;
  }, {});

  const candidateGroups = groupCandidates(candidates);

  return (
    <main className="min-h-screen px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 sm:text-3xl">
              分红资产监控
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              {views.length} 只标的实时建议 ·{' '}
              <span className="text-emerald-400">
                {(actionCounts.buy_now ?? 0) + (actionCounts.small_test ?? 0)} 可建仓
              </span>{' '}
              ·{' '}
              <span className="text-sky-400">
                {actionCounts.watch_active ?? 0} 持仓观察
              </span>{' '}
              ·{' '}
              <span className="text-slate-400">
                {(actionCounts.wait_pullback ?? 0) +
                  (actionCounts.no_action ?? 0)} 暂不建仓
              </span>{' '}
              ·{' '}
              <span className="text-rose-400">
                {actionCounts.avoid ?? 0} 建议剔除
              </span>
            </p>
            <p className="mt-1 text-xs text-slate-500">
              数据更新 {formatBjTime(ts)} · 实时价格刷新自动生效
            </p>
          </div>
          <RefreshButton />
        </header>

        {/* 主仪表盘 — 按 tier 分组 */}
        {(['core', 'supporting', 'watch'] as Tier[]).map((tier) => {
          const items = grouped[tier];
          if (items.length === 0) return null;
          const meta = TIER_TITLES[tier];
          return (
            <section key={tier} className="mb-10">
              <div className="mb-4 flex items-baseline gap-3 border-b border-slate-800 pb-2">
                <h2 className="text-lg font-bold text-slate-100">{meta.title}</h2>
                <span className="text-xs text-slate-500">{meta.subtitle}</span>
                <span className="ml-auto font-mono text-xs text-slate-500">
                  {items.length} 只
                </span>
              </div>
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
                {items.map((view) => (
                  <ProductCard key={view.config.code} view={view} />
                ))}
              </div>
            </section>
          );
        })}

        {/* 候选池 — 按 bucket 分组 */}
        {candidates.length > 0 && (
          <section className="mb-10">
            <div className="mb-4 flex items-baseline gap-3 border-b border-slate-800 pb-2">
              <h2 className="text-lg font-bold text-slate-300">
                🪧 候选池（未进入主仪表盘）
              </h2>
              <span className="ml-auto font-mono text-xs text-slate-500">
                {candidates.length} 只
              </span>
            </div>
            <div className="mb-4 rounded-lg bg-slate-800/30 px-3 py-2 text-xs text-slate-400 ring-1 ring-slate-700">
              <strong className="text-slate-300">说明：</strong>这些标的暂不进入主仪表盘，原因分类如下。
              下方按"修复优先级"排列：
              <span className="text-amber-400"> 缺数据</span> /
              <span className="text-sky-400"> 行业挤出</span> 是可推进的（补数据或调阈值后可入池）；
              <span className="text-slate-500"> 新发不足/yield低/小盘</span> 是结构性问题，等时间或基本面变化即可。
            </div>

            {BUCKET_ORDER.map((bucket) => {
              const items = candidateGroups[bucket];
              if (!items || items.length === 0) return null;
              const meta = BUCKET_META[bucket];
              return (
                <div key={bucket} className="mb-5">
                  <div className="mb-2 flex items-baseline gap-3">
                    <h3 className="text-sm font-semibold text-slate-200">
                      {meta.title}
                    </h3>
                    <span className="text-[11px] text-slate-500">
                      {meta.subtitle}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-slate-500">
                      {items.length} 只
                    </span>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {items.map((c) => (
                      <CandidateCard key={c.code} candidate={c} />
                    ))}
                  </div>
                </div>
              );
            })}
          </section>
        )}

        {/* Footer — 极简 */}
        <footer className="mt-12 border-t border-slate-800 pt-6 text-xs text-slate-500">
          <p>
            <strong className="text-slate-300">建议如何理解</strong>：
            <span className="text-emerald-400"> 立即建仓 / 小仓试水</span> = 价格触发可入；
            <span className="text-sky-400"> 持仓观察</span> = 接近触发等机会；
            <span className="text-slate-400"> 等待回调 / 暂不建仓</span> = 不便宜，再等；
            <span className="text-rose-400"> 建议剔除</span> = 基本面有问题。
          </p>
          <p className="mt-2">
            <strong className="text-slate-300">数据完整度</strong>：每张卡片明确标 ✅
            完整 / ⚠️ 缺。缺数据时不给具体建议。
          </p>
          <p className="mt-3 text-slate-600">
            ⚠️ 仅供研究参考，非投资建议。投资决定需自行核实并承担风险。
          </p>
        </footer>
      </div>
    </main>
  );
}
