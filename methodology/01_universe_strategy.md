# Stage 1 · 全市场宇宙采集策略

## 为什么用"种子列表"而不是"全市场扫描"

最初尝试过两种全市场扫描方案：

1. **东方财富 b:MK0021 板块拉全 ETF**：单页限 100 条，全市场 1173 只 → 12 页分页拉取可行，但耗时
2. **东方财富 b:MK0827 拉 REITs**：实际返回的是商品 ETF（黄金/豆粕），**不是 REITs**
3. **代码段扫描（508xxx + 180xxx 范围）**：1000+ 次调用很容易触发 rate limit

调研结论：东方财富**没有公开的"REITs 全列表" JSON 接口**。可行方案：
- 爬 `https://data.eastmoney.com/reits/` 页面（HTML，需要解析）
- 或用 Tushare REIT 列表 API（需要 token）
- **或维护一份 seed list**，每季度对照官方披露刷新

我们选**第三方案 — seed list**，原因：
- ✅ 稳定可重现（不依赖第三方未公开 API）
- ✅ API 压力小（每只 1 次 quote 调用即可，~50 次总）
- ✅ 来源可追溯（每个代码标注采集源 + 日期）
- ❌ 需要每季度更新一次（手动或用 DeepSeek 辅助）

## Seed list 来源

`methodology/seed_universe.json` 里的代码来源：

1. **公募 REITs**：上海证券交易所 / 深圳证券交易所披露的"公募 REITs 列表"
   - 上交所：[https://www.sse.com.cn/reits/](https://www.sse.com.cn/reits/)
   - 深交所：[http://reits.szse.cn/](http://reits.szse.cn/)
2. **红利 ETF**：东方财富 ETF 板块 + 中证指数公司红利系列指数对应 ETF
3. **港股红利 QDII**：东方财富 QDII 板块筛选名字含"港股"+"红利"

## 季度刷新流程

```bash
# 1. 让 DeepSeek 生成最新候选列表（基于训练数据 + 公开信息）
npm run screen:00-refresh-seed

# 2. 人工 review diff（输出到 data/seed_diff.json）
git diff methodology/seed_universe.json

# 3. 确认后 commit
```

或手动：

1. 打开上交所 / 深交所 REITs 披露页
2. 对照 `seed_universe.json`，新增上市的产品添加进去
3. 已退市/合并的标记 `status: "delisted"`

## seed_universe.json schema

```ts
interface SeedEntry {
  code: string;                   // 6 位代码
  market: 'sh' | 'sz';
  name: string;                   // 简称（用东方财富展示名）
  category: 'dividend_etf_a' | 'dividend_etf_hk' | 'reit';
  reit_subtype?: 'consumption' | 'rental_housing' | 'energy' | 'transportation' | 'logistics' | 'park' | 'municipal';
  source: string;                 // 例如 "SSE REITs 披露页 2026-04-28"
  added_at: string;               // ISO date
  status: 'active' | 'delisted' | 'pending';
  notes?: string;
}
```

## 扩展原则

- **宁可多不要漏**：seed 多了，Stage 3 量化筛选会过滤；少了就再无机会进入候选
- **类别明确**：每个 seed 必须能归类到 framework 内一个 reit_subtype，否则 Stage 3 会把它标 `other` 淘汰
- **代码格式严格**：6 位字符串。不要用整数（保留 leading 0）

## 与 Stage 2-5 的关系

Stage 1（本步）只产生**有效代码列表**：

```json
{
  "fetchedAt": "...",
  "from_seed": 87,
  "validated": 84,           // 实时 quote 能拿到数据
  "delisted_or_invalid": 3,  // quote 失败的
  "dividend_etfs": [...],    // 元数据从 quote API 拿
  "reits": [...]
}
```

Stage 2 拉历史数据时直接用这个列表，不再做发现。
