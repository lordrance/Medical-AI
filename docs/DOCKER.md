# Docker 化指南

> 这个项目的 **Docker 化策略**：开发/生产分两套 compose；前端开发期本地跑（HMR 体验），生产期容器化。

---

## 1. 哪些组件值得 Docker 化（结论先行）

| 组件 | 推荐度 | 原因 |
| --- | --- | --- |
| **Postgres** | ⭐⭐⭐ 必装 | 比本地装 PG 快 10 倍；数据卷自动持久化 |
| **后端 FastAPI** | ⭐⭐⭐ 必装 | Python 依赖、`asyncpg`/`aiosqlite` 跨 OS 一致 |
| **Nginx 反代** | ⭐⭐⭐ 生产必用 | 同源、HTTPS 终端、限流、CORS 简化 |
| **前端 Next.js** | ⭐⭐ 生产推荐；开发不用 | 生产 multi-stage 镜像 ~150 MB；开发本地 `pnpm dev` HMR 更快 |
| **Postgres 备份 cron** | ⭐⭐ 推荐 | 同进程容器，每天 `pg_dump` |
| **DeepSeek API** | ❌ 不容器化 | 外部 SaaS，HTTP 调用即可 |

---

## 2. 文件清单

```
docker-compose.yml           # 开发：db + backend
docker-compose.prod.yml      # 生产：db + backend + frontend* + nginx + backup
backend/Dockerfile           # multi-stage：builder → slim runtime（非 root）
backend/docker/entrypoint.sh # 启动时 wait_for_db → alembic upgrade → seed → exec
docker/nginx/nginx.conf      # 反代 + /api 限流 60 req/min
.env.example                 # 顶层 compose 变量模板
```

> 前端容器化在 Phase 3 落地，prod compose 已留好 stub。

---

## 3. 开发环境：5 分钟跑起来

```bash
git clone https://github.com/lordrance/Medical-AI.git
cd Medical-AI
git checkout cursor/v2-fastapi-cn-redesign-8fc6
cp .env.example .env

# 一键启动 db + backend
docker compose up --build

# 浏览器：
# http://localhost:8000/docs       Swagger UI
# http://localhost:8000/healthz
```

启动时 entrypoint 会自动：
1. 等 Postgres 起来（最多 60 秒）
2. `alembic upgrade head` 应用所有迁移
3. `python -m app.scripts.seed` 灌入中文 case + 顺序模板（幂等 upsert）
4. 启 uvicorn

可关掉的步骤：

```bash
RUN_MIGRATIONS=false SEED_ON_START=false docker compose up
```

---

## 4. 启用 DeepSeek

```bash
# .env 或者 export
LLM_PROVIDER=deepseek
LLM_DRY_RUN=false
DEEPSEEK_API_KEY=sk-xxxxx

docker compose up --build
```

如果 `LLM_PROVIDER=deepseek` 但 key 为空，后端会自动 fallback 到 `DryRunProvider`，不会启动失败。这样开发阶段非常友好。

---

## 5. 生产环境

需要先在 `.env` 设置三个**必填**变量：

```bash
POSTGRES_PASSWORD=<a strong random>
ADMIN_TOKEN=<a strong random>
DEEPSEEK_API_KEY=<your sk-xxxxx>      # 可选，关 LLM 时留空
CORS_ORIGINS=["https://your-domain.com"]
```

然后：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

服务包括：

- `db`：Postgres 15-alpine + 数据卷
- `backend`：自动跑 migration + seed 后启 uvicorn（healthcheck 30s）
- `nginx`：80 端口反代，`/api/*` 60 req/min 限流
- `backup`：每天 `pg_dump` 到 `./backups/`（保留最近 30 份）
- `frontend`（Phase 3）

> HTTPS 部署建议：在 nginx 容器外再加一层（Caddy / Cloudflare Tunnel / 阿里云 CDN）做 TLS 终端，最简单。

---

## 6. 常用运维命令

```bash
# 查看实时日志
docker compose logs -f backend
docker compose logs -f db

# 进入后端容器
docker compose exec backend bash

# 跑 pytest
docker compose exec backend pytest -q

# 手动备份一次
docker compose -f docker-compose.prod.yml exec backup \
  pg_dump --format=custom --file=/backups/manual-$(date +%s).dump

# 恢复备份
docker compose -f docker-compose.prod.yml exec backup \
  pg_restore --clean --if-exists --dbname=medai /backups/<file>.dump

# 销毁所有数据（pilot 重置）
docker compose down -v
```

---

## 7. 镜像大小目标

| 阶段 | 镜像 | 目标大小 |
| --- | --- | --- |
| backend builder | 临时 | ~600 MB（含编译工具） |
| **backend runtime** | 实际部署 | **~250 MB**（slim + venv） |
| frontend (Phase 3) | next.js standalone | **~150 MB** |
| postgres:15-alpine | 官方 | ~80 MB |
| nginx:1.27-alpine | 官方 | ~50 MB |

---

## 8. CI/CD 建议

```yaml
# .github/workflows/build.yml (Phase 7 落地)
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - run: docker compose build
      - run: docker compose run --rm backend pytest -q
```

---

## 9. 安全要点

- `ADMIN_TOKEN` 不要弱 token，使用 `openssl rand -hex 32`
- `DEEPSEEK_API_KEY` 放 `.env`（已 gitignore），永不进 git
- `Dockerfile` 用非 root `app` 用户运行
- nginx 加了 `limit_req` 防接口滥用
- 部署在国内云时，数据库不暴露公网（compose 已默认只暴露 80 / 8000）

---

## 10. 部署到云的最小路径

1. 买台 2C4G 云主机（阿里云 / 腾讯云上海或北京）
2. `apt install docker.io docker-compose-plugin`
3. `git clone` + `cp .env.example .env` + 改密钥
4. `docker compose -f docker-compose.prod.yml up -d --build`
5. DNS 把域名指向主机 IP
6. 在 nginx 前面加 Cloudflare（免费 HTTPS + WAF + 限流）即可上线

总成本：服务器 80 元/月 + 域名 50 元/年 + DeepSeek 按量。
