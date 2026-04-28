# 分红资产监控 · Stock Monitor

低风险分红/分派资产实时监控仪表盘。Next.js 14 + Vercel 部署友好。

## 监控池（v0.2 · 12 个标的）

### A 股红利 ETF（4 只 · 横向对比）

| 代码 | 名称 | 角色 |
| --- | --- | --- |
| `515100` | 红利低波 100 ETF（景顺长城）| 100 只样本，行业上限 20%，规模 64 亿（同类最大）|
| `512890` | 红利低波 ETF（华泰柏瑞）| 50 只样本，规模 300+ 亿，A 股首只红利低波 |
| `510880` | 上证红利 ETF（华泰柏瑞）| 国内最老牌红利 ETF（2006），上证红利指数 |
| `561580` | 央企红利 ETF（华泰柏瑞）| 央企抗周期，分红稳定性高于民企 |

### 港股红利 ETF（1 只 · 高股息）

| 代码 | 名称 | 角色 |
| --- | --- | --- |
| `513530` | 港股通红利 ETF（华泰柏瑞 QDII）| 港股高股息，QDII 模式有红利税优势（vs 港股通 20%）|

### 公募 REITs（7 只 · 全分支覆盖）

| 代码 | 名称 | 类型 | 备注 |
| --- | --- | --- | --- |
| `180601` | 华夏华润商业 REIT | 消费/商业 | 青岛万象城，已公告扩募 |
| `180602` | 中金印力消费 REIT | 消费/商业 | 杭州西溪印象城，2024 年新盘 |
| `180202` | 华夏越秀高速 REIT | 交通基建 | 高速公路，机构最爱（4-5 次/年分红）|
| `508077` | 华夏基金华润有巢 REIT | 保租房 | 上海保租房，类债资产 |
| `508058` | 中金厦门安居 REIT | 保租房 | 厦门核心保租房 |
| `508028` | 中信建投国家电投新能源 REIT | 能源基建 | 江苏海上风电 |
| `508098` | 嘉实京东仓储基础设施 REIT | 仓储物流 | 京东自用仓库（廊坊/武汉/重庆）|

> **Gemini 错误已修正**：原 Gemini 对话里推荐的 `513330`（标普500红利贵族）实际是华夏恒生互联网科技 ETF（港股科技股）；`512890` 不是港股通而是 A 股红利低波。监控池已替换为正确代码。

> **未纳入监控的标的**：
> - 黄金 ETF (`518880`) / 标普 500 ETF (`513500`)：不分红或不通过分红派息，当前 signal 模型（基于实时分派率）不适用，会一直显示 HOLD。这两个属于"价值/抗通胀"决策模型（看 PE 或价格分位），需要独立的 signal 逻辑，留给未来版本做单独面板。
> - 大额存单 / 短债基金 / 货币基金：现金管理层无"买入信号"概念（始终在线），不是这个仪表盘的对象。建议直接在券商 App / 银行端管理。

## 信号逻辑

每个标的 3 档信号：

- **HOLD**：等更便宜，不动
- **WATCH**：进入观察区，可小仓位试水（10-30% 配置量）
- **BUY**：满足建仓条件，可分批入场

判定规则（任一命中即升档）：

1. 实时分派率（= TTM 分红 / 当前价）≥ `buyYield` → BUY；≥ `watchYield` → WATCH
2. 当前价 ≤ `buyPrice` → BUY；≤ `watchPrice` → WATCH（仅 REITs 用）

阈值在 [lib/products.ts](lib/products.ts) 里配置。改一下就 hot reload 生效。

## 快速开始

需要 Node.js ≥ 18。

```bash
npm install
npm run dev          # http://localhost:3000
```

打开浏览器即看到仪表盘。点击右上角"刷新数据"重新拉行情（缓存 60 秒，即使猛点也不会打爆东方财富）。

### 调试单个标的

```bash
curl http://localhost:3000/api/quote/515100
```

返回该标的的完整 config / quote / signal JSON。

## 手动维护

### 更新 TTM 分红

每只标的的 `ttmDividend` 是手动维护的（公开数据没有便利的 JSON 接口）。当公告新一期分红时：

1. 打开 [lib/products.ts](lib/products.ts)
2. 找到对应代码
3. 把过去 12 个月分红总额（元/份）填到 `ttmDividend`
4. 更新 `ttmDividendAsOf` 为今天日期
5. 提交即可，下次刷新生效

数据来源：
- ETF 分红：[天天基金 fhsp 页面](http://fundf10.eastmoney.com/fhsp_180601.html)（替换代码即可）
- REIT 分红：上交所/深交所披露的"收益分配公告"PDF

### 调整阈值

策略变了就改 `watchYield` / `buyYield` / `watchPrice` / `buyPrice`。

### 增删标的

在 `PRODUCTS` 数组里增删。`market` 字段必须填：沪市（5/1/6 开头）填 `'sh'`，深市（0/3 开头）填 `'sz'`。

## 数据源

行情：[push2.eastmoney.com](https://push2.eastmoney.com)（东方财富公开接口）

- 免费、无鉴权、无频率限制（合理使用）
- ETF / REITs / 股票通用，secid 规则：`1.{code}` 沪市，`0.{code}` 深市
- Server Component `fetch` 内置缓存 60 秒（见 [lib/eastmoney.ts](lib/eastmoney.ts)）

## 部署到 Vercel

### 一次性设置

```bash
npm i -g vercel
vercel login
vercel link            # 把当前目录关联到一个 Vercel 项目
vercel --prod          # 首次部署
```

或者直接在 Vercel 网页：
1. 把这个 repo push 到 GitHub
2. [vercel.com/new](https://vercel.com/new) → 选 repo → Deploy
3. Vercel 自动识别 Next.js，零配置

部署完拿到 `https://xxx.vercel.app` 就能用。

### Vercel 平台注意

- **Hobby plan 限制**：单次函数 10s（够用，6 个标的并发 fetch 一般 < 2s），月免费额度 100GB-Hours
- **时区**：Vercel 服务器是 UTC，代码内已用 `Asia/Shanghai` 显式格式化时间
- **`.vercelignore`** 已排除 OpenClaw 工作区文件（`memory/`、`skills/` 等），不会进部署包

### 后续：定时任务（暂不启用）

Vercel Cron 可以做"每天收盘后跑一次"。当通知通道定下来时，加 `vercel.json`：

```json
{
  "crons": [
    { "path": "/api/cron/refresh", "schedule": "30 7 * * 1-5" }
  ]
}
```

`30 7 * * 1-5` = UTC 7:30 = 北京时间 15:30（A 股收盘后）。需要新写 `app/api/cron/refresh/route.ts` 处理推送逻辑。

## 项目结构

```
.
├── app/
│   ├── layout.tsx              # 根 layout
│   ├── page.tsx                # 仪表盘（Server Component）
│   ├── actions.ts              # Server Action：刷新缓存
│   ├── globals.css             # Tailwind base
│   └── api/
│       └── quote/[code]/       # 单标的调试 API
├── components/
│   ├── ProductCard.tsx         # 产品卡片
│   ├── SignalBadge.tsx         # HOLD/WATCH/BUY 徽章
│   └── RefreshButton.tsx       # 客户端刷新按钮
├── lib/
│   ├── types.ts                # TS 类型定义
│   ├── products.ts             # 监控池配置（手动维护）
│   ├── eastmoney.ts            # 东方财富数据源
│   ├── signals.ts              # 信号判定逻辑
│   └── format.ts               # 格式化工具
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.mjs
├── postcss.config.js
├── .vercelignore               # 排除 OpenClaw workspace 文件
└── .gitignore
```

## 路线图（未实现）

- [ ] 通知通道（飞书 / 微信 / 邮件，待选）
- [ ] Vercel Cron 收盘后自动比对
- [ ] 历史数据存储（Vercel KV / Postgres），画分派率百分位曲线
- [ ] 填权监控（分红后股价回归速度）
- [ ] 扩募/解禁公告爬虫（上交所/深交所）
- [ ] 分红日历（下次分红预测）
- [ ] 标普500/海外暴露的 ETF 选型补充

## ⚠️ 免责声明

仅供研究使用，非投资建议。任何投资决定需自行核实数据并承担风险。
