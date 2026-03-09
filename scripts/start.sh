#!/bin/bash
# =============================================================================
# Media Hosting Suite — 一键启动脚本
# 启动/重启所有服务: Nginx + Media API + Tunnel Agent
# 用法: bash start.sh
# =============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }

echo "========================================"
echo "  Media Hosting Suite — 启动中"
echo "========================================"

start_service() {
  local name="$1"
  systemctl start "$name" 2>/dev/null
  if systemctl is-active --quiet "$name"; then
    ok "$name"
  else
    fail "$name (尝试重启...)"
    systemctl restart "$name" 2>/dev/null || true
    sleep 2
    systemctl is-active --quiet "$name" && ok "$name (重启成功)" || fail "$name 启动失败，请检查: journalctl -u $name -n 20"
  fi
}

start_service nginx
start_service image-api
start_service images-tunnel

echo ""
echo "========================================"
echo "  服务状态汇总"
echo "========================================"

for svc in nginx image-api images-tunnel; do
  status=$(systemctl is-active "$svc" 2>/dev/null)
  if [ "$status" = "active" ]; then
    ok "$svc: $status"
  else
    fail "$svc: $status"
  fi
done

echo ""
echo "  API:    http://127.0.0.1:1002"
echo "  管理:   http://127.0.0.1:1002/admin"
PUBBASE=$(grep PUBLIC_BASE /opt/image-api/.env 2>/dev/null | cut -d= -f2)
if [ -n "$PUBBASE" ]; then
  echo "  公网:   $PUBBASE"
fi
echo "========================================"
