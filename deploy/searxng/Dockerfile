# SearXNG 自定义镜像 — 基于官方镜像 + 内嵌 settings.yml
FROM searxng/searxng:latest

# 把我们的 settings.yml 烤进镜像，避免依赖 fly.io volume 挂载
COPY settings.yml /etc/searxng/settings.yml

# searxng 默认监听 8080
EXPOSE 8080
