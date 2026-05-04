# SearXNG on fly.io

把本地 Docker 跑的 SearXNG 搬到云上，让 Vercel 部署的 dashboard / cron 可以远程调用。

## 部署步骤（首次）

```bash
cd deploy/searxng

# 1. 创建 fly.io 应用（不立即部署）
#    --name 填一个全局唯一的名字，例：stock-searxng-yufeng
flyctl launch --no-deploy --copy-config --name stock-searxng-<你的名字>

# 2. 设置 secret_key（生产环境必须用强随机 key）
flyctl secrets set SEARXNG_SECRET_KEY="$(openssl rand -hex 32)"
# Windows PowerShell 用：
#   flyctl secrets set SEARXNG_SECRET_KEY=$(-join ((48..57)+(97..122) | Get-Random -Count 64 | %{[char]$_}))

# 3. 部署
flyctl deploy

# 4. 拿 URL（输出形如 https://stock-searxng-yufeng.fly.dev）
flyctl status

# 5. 验证 JSON API 能用
curl "https://stock-searxng-<你的名字>.fly.dev/search?q=test&format=json" | jq .results[0]
```

## 后续维护

```bash
# 查看运行状态
flyctl status

# 看日志（debug 用）
flyctl logs

# 改 settings.yml 后重新部署
flyctl deploy

# 释放（如果不用了）
flyctl apps destroy stock-searxng-<你的名字>
```

## 成本

free tier 包含：
- 3 个 shared-cpu-1x（256MB-512MB）VM
- 160GB 出站流量/月
- HTTPS 自动证书

我们配了 `auto_stop_machines = stop` + `min_machines_running = 0`，闲置 5 分钟后停机，
有请求自动启（冷启 ~3-5 秒）。月成本预估 **$0**。

## 在代码里使用

部署完后，在项目根 `.env` 里加：

```
SEARXNG_URL=https://stock-searxng-<你的名字>.fly.dev
```

`scripts/_lib/searxng.mjs` 已经支持这个环境变量；本地不设的话默认 `http://localhost:8890`。
