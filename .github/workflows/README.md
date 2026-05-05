# GitHub Actions Cron — 数据自动刷新管道

## 工作流概览

| 工作流 | 频率 | 任务 | 月成本 |
|--------|------|------|--------|
| `refresh-ttm.yml` | 每周一 06:00 (BJT) | TTM 分红刷新（fundf10） | ¥0 |
| `refresh-phase2.yml` | 仅手动触发 | Phase 2 评估刷新 | ~¥3/触发 |

未来计划添加：
- `scan-universe.yml` — 月度扫新发标的（能力 4 待建）

## 必需的 GitHub Secrets

到仓库 Settings → Secrets and variables → Actions → New repository secret 添加：

| Secret 名 | 值 | 用途 |
|-----------|-----|------|
| `DOUBAO_API_KEY` | 火山引擎 ark API key | Doubao 模型调用 |
| `SEARXNG_URL` | `https://stock-searxng-production.up.railway.app` | 云端搜索 |
| `DEEPSEEK_API_KEY` | DeepSeek API key | 备用模型（可选） |

注：`GITHUB_TOKEN` 由 Actions runner 自动提供，不需要手动设置（用于 commit + push）。

## 触发方式

### 手动触发（任何时候）
仓库 → Actions tab → 选工作流 → Run workflow

### 定时触发（自动）
- TTM: 每周一 06:00 北京时间（即 UTC 周日 22:00）
- Phase 2: 当前未启用 schedule，待"增量刷新"脚本完成后启用

## 调试

每次运行的日志都在 Actions 页面。如果 cron 没按时跑，可能原因：
1. 仓库 60 天没活动 → schedule 自动停止（推一次新 commit 重新激活）
2. Secret 没配 → 报错 "GITHUB_TOKEN not set" 等
3. Railway SearXNG 挂了 → 改 SEARXNG_URL 或临时切回 fallback

## 数据流

```
GitHub Actions 触发
  └─ 跑脚本（调 Doubao + SearXNG + Jina + fundf10）
      └─ 写本地 fs (data/*.json)
          └─ git commit + push
              └─ 触发 Vercel rebuild
                  └─ dashboard 显示最新数据
```
