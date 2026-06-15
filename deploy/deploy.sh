#!/usr/bin/env bash
# Medical-AI 生产环境自动部署脚本（由 GitHub Actions 触发）
#
# 在服务器上执行：
#   1. git pull V5 最新代码
#   2. docker compose pull 拉 ghcr.io 上的预构建镜像
#   3. docker compose up -d 替换运行中的容器
#   4. 轮询最多 120s 直到所有容器 healthy
#
# 使用方式（服务器本地调试）：
#   IMAGE_TAG=V5-abc1234 bash deploy/deploy.sh

set -euo pipefail

REPO_DIR="${HOME}/Medical-AI"
COMPOSE_FILE="docker-compose.prod.yml"

# --- 颜色 ---------------------------------------------------------------
RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
log()  { echo "${BLUE}[deploy]${RESET} $*"; }
warn() { echo "${YELLOW}[deploy]${RESET} $*"; }
fail() { echo "${RED}[deploy]${RESET} $*" >&2; exit 1; }
ok()   { echo "${GREEN}[deploy]${RESET} $*"; }

# --- 1. 进入仓库目录 ----------------------------------------------------
if [ ! -d "${REPO_DIR}" ]; then
  fail "仓库目录 ${REPO_DIR} 不存在"
fi
cd "${REPO_DIR}"

log "拉取 V5 分支最新代码..."
git fetch origin V5
git reset --hard origin/V5
ok "代码已更新至 $(git rev-parse --short HEAD)"

# --- 2. 拉取镜像 --------------------------------------------------------
log "拉取最新 Docker 镜像..."
IMAGE_TAG="${IMAGE_TAG:-latest}"
export IMAGE_TAG
docker compose -f "${COMPOSE_FILE}" pull
ok "镜像拉取完成 (IMAGE_TAG=${IMAGE_TAG})"

# --- 3. 重新部署服务 ----------------------------------------------------
log "重新创建服务容器..."
docker compose -f "${COMPOSE_FILE}" up -d
ok "服务容器已启动"

# --- 4. 轮询等待所有服务 healthy -----------------------------------------
log "等待所有服务通过健康检查（最长 120 秒）..."

poll_healthy() {
  docker compose -f "${COMPOSE_FILE}" ps --format json 2>/dev/null \
    | python3 -c "
import sys, json

raw = sys.stdin.read().strip()
if not raw:
    sys.exit(1)

try:
    containers = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(1)

if not isinstance(containers, list):
    sys.exit(1)

total = len(containers)
unhealthy = 0
for c in containers:
    # Health is empty string '' for containers without a healthcheck —
    # skip those (only count containers that *have* a healthcheck).
    health = c.get('Health', '')
    if health and health != 'healthy':
        unhealthy += 1

# stdout: total_count unhealthy_count
print(f'{total} {unhealthy}')
"
}

for i in $(seq 1 60); do
  POLL_RESULT="$(poll_healthy 2>/dev/null || true)"
  TOTAL_COUNT="$(printf '%s' "${POLL_RESULT}" | cut -d' ' -f1)"
  UNHEALTHY_COUNT="$(printf '%s' "${POLL_RESULT}" | cut -d' ' -f2)"

  # Default to 0 if polling failed (e.g., no containers yet)
  TOTAL_COUNT="${TOTAL_COUNT:-0}"
  UNHEALTHY_COUNT="${UNHEALTHY_COUNT:-0}"

  if [ "${TOTAL_COUNT}" -eq 0 ]; then
    log "尚无容器就绪，等待..."
  elif [ "${UNHEALTHY_COUNT}" -eq 0 ]; then
    ok "所有 ${TOTAL_COUNT} 个容器已通过健康检查"
    break
  else
    log "${UNHEALTHY_COUNT}/${TOTAL_COUNT} 个容器尚未 healthy，等待..."
  fi
  sleep 2
done

# 最终状态检查
FINAL_RESULT="$(poll_healthy 2>/dev/null || echo '0 1')"
FINAL_UNHEALTHY="$(printf '%s' "${FINAL_RESULT}" | cut -d' ' -f2)"

if [ "${FINAL_UNHEALTHY}" -gt 0 ]; then
  warn "${FINAL_UNHEALTHY} 个容器仍未通过健康检查。请手动排查:"
  warn "  docker compose -f ${COMPOSE_FILE} ps"
  warn "  docker compose -f ${COMPOSE_FILE} logs"
  fail "部署异常"
fi

echo
ok "${BOLD}部署成功！${RESET}"
echo "  镜像标签: ${IMAGE_TAG}"
echo "  提交:     $(git rev-parse --short HEAD)"
echo "  时间:     $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
