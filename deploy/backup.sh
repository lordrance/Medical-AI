#!/usr/bin/env bash
# 一键备份当前数据：pg_dump + 录音文件 → 一个 .tar.gz 包。
#
# 自动备份的「backup」容器每天会跑一次 pg_dump 到 ./backups/。
# 这个脚本是「我现在就想立刻打包带走全部数据」的快捷方式。
#
# 用法（在服务器上）：
#   bash deploy/backup.sh
# 然后在你自己电脑上拉走：
#   scp root@<server>:/root/Medical-AI/backups/medical-ai-*.tar.gz .

set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p backups
TS="$(date +%Y%m%d_%H%M%S)"
OUT="backups/medical-ai-${TS}"
mkdir -p "${OUT}"

echo "[backup] 1/3 pg_dump 整库..."
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump --format=custom -U "${POSTGRES_USER:-medai}" "${POSTGRES_DB:-medai}" \
  > "${OUT}/database.dump"

echo "[backup] 2/3 拷贝录音文件..."
if [ -d data/voice_recordings ] && [ -n "$(ls -A data/voice_recordings 2>/dev/null || true)" ]; then
  cp -r data/voice_recordings "${OUT}/voice_recordings"
else
  echo "  (无录音文件)"
fi

echo "[backup] 3/3 打 tar.gz..."
tar -czf "${OUT}.tar.gz" -C backups "$(basename "${OUT}")"
rm -rf "${OUT}"

SIZE="$(du -h "${OUT}.tar.gz" | cut -f1)"
echo
echo "✅ 备份完成：${OUT}.tar.gz （${SIZE}）"
echo
echo "在你自己电脑上跑下面命令拉到本地："
echo "  scp root@<服务器IP>:$(pwd)/${OUT}.tar.gz ."
