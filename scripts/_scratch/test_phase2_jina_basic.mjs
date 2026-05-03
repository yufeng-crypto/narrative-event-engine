/**
 * Phase 2 - Step 1：验证 Jina Reader 能不能从巨潮/上交所/搜狐财经等抓到
 * REIT 年报关键章节。
 *
 * 测试目标：508056 中金普洛斯REIT 2024年报 → 找"商誉减值"/"9889"。
 * 流程：SearXNG 搜年报 → 取前几个 URL → Jina fetch → grep 关键词
 *
 * 验收标准：能在 markdown 里找到 "商誉" 或 "9889" 字样 → Phase 2 可行
 *
 * 用法：node --env-file=.env scripts/_scratch/test_phase2_jina_basic.mjs
 */

import { searxngSearch } from '../_lib/searxng.mjs';
import { fetchUrl } from '../_lib/jina_reader.mjs';

const QUERY = '508056 中金普洛斯 2024年报 商誉减值';
const TARGET_KEYWORDS = ['商誉', '9889', '减值', '净利润', '可分配'];

async function main() {
  console.log('Phase 2 - Jina 可行性验证');
  console.log('Target: 508056 中金普洛斯 2024 商誉减值 9889 万');
  console.log('---');

  // 1. SearXNG 搜
  console.log('1. SearXNG 搜索:', QUERY);
  const sr = await searxngSearch(QUERY, { topN: 8 });
  console.log(`   → ${sr.count} results`);
  for (let i = 0; i < Math.min(sr.results.length, 5); i++) {
    const r = sr.results[i];
    console.log(`   [${i}] ${r.title.slice(0, 50)}`);
    console.log(`       ${r.url}`);
  }
  console.log('');

  // 2. 选前 4 条来 fetch
  console.log('2. Jina Reader fetch 前 4 条:');
  const fetches = await Promise.all(
    sr.results.slice(0, 4).map((r, i) =>
      fetchUrl(r.url, { maxChars: 50000 }).then((res) => ({
        idx: i,
        title: r.title,
        sourceUrl: r.url,
        ...res,
      }))
    )
  );

  for (const f of fetches) {
    if (f.error) {
      console.log(`   [${f.idx}] ✗ ${f.title.slice(0, 40)} → ${f.error}`);
      continue;
    }
    const hits = TARGET_KEYWORDS.map((kw) => ({
      kw,
      hit: f.markdown.includes(kw),
    }));
    const hitStr = hits.map((h) => `${h.kw}:${h.hit ? '✓' : '✗'}`).join(' ');
    console.log(
      `   [${f.idx}] ✓ ${f.title.slice(0, 40)} ` +
        `(${(f.length / 1000).toFixed(1)}K chars${f.truncated ? ', truncated' : ''}) ${hitStr}`
    );
  }

  // 3. 选 hit 数最多的那个，看具体上下文
  console.log('');
  console.log('3. 找命中"商誉"或"9889"的最佳源：');
  const ranked = fetches
    .filter((f) => !f.error)
    .map((f) => ({
      ...f,
      score:
        (f.markdown.includes('商誉') ? 2 : 0) +
        (f.markdown.includes('9889') ? 5 : 0) +
        (f.markdown.includes('减值') ? 1 : 0),
    }))
    .sort((a, b) => b.score - a.score);

  if (ranked.length === 0 || ranked[0].score === 0) {
    console.log('   ❌ 4 个源都没找到关键字');
    console.log('   ⚠️ 需要扩大搜索范围或换 query');
    return;
  }

  const best = ranked[0];
  console.log(`   ✅ best: ${best.title.slice(0, 50)} (score ${best.score})`);
  console.log(`   url: ${best.sourceUrl}`);
  console.log('');

  // 找包含"商誉"的段落
  for (const kw of ['9889', '商誉']) {
    const idx = best.markdown.indexOf(kw);
    if (idx >= 0) {
      const start = Math.max(0, idx - 200);
      const end = Math.min(best.markdown.length, idx + 400);
      console.log(`   "${kw}" 上下文（±300字）:`);
      console.log('   > ' + best.markdown.slice(start, end).replace(/\n+/g, ' ').slice(0, 600));
      console.log('');
      break; // 只看一个就够了
    }
  }

  console.log('---');
  console.log('结论：');
  console.log(
    ranked[0].score >= 5
      ? '✅ Phase 2 可行 — Jina 拉到了关键数字（9889），可以让 Doubao 读全文挖深层事实'
      : ranked[0].score >= 2
      ? '⚠️ 部分可行 — 找到关键词但没找到具体数字，可能需要换源（例如直接查招股说明书 PDF）'
      : '❌ Phase 2 不可行 — Jina 没拉到关键章节，需要换 Crawl4AI 或换源'
  );
}

main().catch((e) => {
  console.error('Failed:', e);
  process.exit(1);
});
