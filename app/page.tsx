import { CandidateCard } from '@/components/CandidateCard';
import { ProductCard } from '@/components/ProductCard';
import { RefreshButton } from '@/components/RefreshButton';
import { loadCandidates } from '@/lib/candidates';
import { fetchEastMoneyQuote } from '@/lib/eastmoney';
import { formatBjTime } from '@/lib/format';
import { PRODUCTS, TIER_ORDER } from '@/lib/products';
import { evaluateSignal } from '@/lib/signals';
import type { ProductView, Tier } from '@/lib/types';

export const dynamic = 'force-dynamic';

const TIER_TITLES: Record<Tier, { title: string; subtitle: string }> = {
  core: {
    title: '🥇 核心持仓池',
    subtitle: 'A+ 级 · 央企背景 + 扩募预期 + 政策强支持，可优先建仓',
  },
  supporting: {
    title: '🥈 辅助持仓池',
    subtitle: 'A 级 · 合格但有特殊处理（关注 Red Flags）',
  },
  watch: {
    title: '🥉 监控池',
    subtitle: 'A 级低分 · 留池但暂不建仓（与核心重叠 / 边际不足）',
  },
};

async function loadView(): Promise<{
  views: ProductView[];
  ts: string;
}> {
  const views = await Promise.all(
    PRODUCTS.map(async (config) => {
      const quote = await fetchEastMoneyQuote(config.code, config.market);
      const signal = evaluateSignal(config, quote);
      return { config, quote, signal };
    }),
  );
  return { views, ts: new Date().toISOString() };
}

export default async function HomePage() {
  const { views, ts } = await loadView();
  const candidates = loadCandidates();

  const buyCount = views.filter((v) => v.signal.level === 'buy_now').length;
  const watchCount = views.filter((v) => v.signal.level === 'watch').length;

  // 按 tier 分组，然后每组内按 signal 等级 + score 排序
  const signalOrder: Record<string, number> = { buy_now: 0, watch: 1, hold: 2 };
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
      const sa = signalOrder[a.signal.level] - signalOrder[b.signal.level];
      if (sa !== 0) return sa;
      return (b.config.qualityScore ?? 0) - (a.config.qualityScore ?? 0);
    });
  }

  return (
    <main className="min-h-screen px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 sm:text-3xl">
              分红资产监控
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              400w 资金低风险分红配置 ·{' '}
              <span className="font-mono">
                {buyCount} BUY / {watchCount} WATCH /{' '}
                {views.length - buyCount - watchCount} HOLD
              </span>{' '}
              · 共 {views.length} 只标的
            </p>
            <p className="mt-1 text-xs text-slate-500">
              数据更新于 {formatBjTime(ts)} · 北京时间 · 数据源
              push2.eastmoney.com（缓存 60 秒）
            </p>
          </div>
          <RefreshButton />
        </header>

        {(['core', 'supporting', 'watch'] as Tier[]).map((tier) => {
          const items = grouped[tier];
          if (items.length === 0) return null;
          const meta = TIER_TITLES[tier];
          return (
            <section key={tier} className="mb-10">
              <div className="mb-4 flex items-baseline gap-3 border-b border-slate-800 pb-2">
                <h2 className="text-lg font-bold text-slate-100">
                  {meta.title}
                </h2>
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

        {candidates.length > 0 && (
          <section className="mb-10">
            <div className="mb-4 flex items-baseline gap-3 border-b border-slate-800 pb-2">
              <h2 className="text-lg font-bold text-slate-300">
                🪧 候选池（未入选）
              </h2>
              <span className="text-xs text-slate-500">
                seed_universe 里、Stage 3 量化筛选未通过的标的，下次复跑流水线时可能升级
              </span>
              <span className="ml-auto font-mono text-xs text-slate-500">
                {candidates.length} 只
              </span>
            </div>
            <div className="mb-3 rounded-lg bg-amber-500/5 px-3 py-2 text-xs text-amber-300/80 ring-1 ring-amber-500/20">
              ⚠️ 注意：dividend API 当前不可用，导致 REIT-H3（近 12 月无分红）和
              REIT-H7（分派率 &lt; 3.5%）出现大量误判 — 实际上这些标的可能是有分红的，
              下次跑流水线时只要 manual_dividend_overrides.json 补全或 API 恢复，就能正常评估
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {candidates.map((c) => (
                <CandidateCard key={c.code} candidate={c} />
              ))}
            </div>
          </section>
        )}

        <footer className="mt-12 border-t border-slate-800 pt-6 text-xs text-slate-500">
          <p>
            <strong className="text-slate-300">分级方法</strong>：来自完整 5 阶段流水线（
            <code className="rounded bg-slate-800 px-1">scripts/01-05</code>），由
            DeepSeek API 跑 6 维度评分，Opus 做最终把关。详见{' '}
            <code className="rounded bg-slate-800 px-1">methodology/</code>
          </p>
          <p className="mt-2">
            <strong className="text-slate-300">阈值逻辑</strong>：实时分派率 ≥
            buyYield 或价格 ≤ buyPrice → BUY；之间 → WATCH；否则 → HOLD。
          </p>
          <p className="mt-2 text-slate-600">
            ⚠️ 仅供研究使用，非投资建议。任何投资决定需自行核实数据。
          </p>
        </footer>
      </div>
    </main>
  );
}
