#!/bin/bash
# =============================================================================
# Media Hosting Suite — 一键安装脚本
# 覆盖范围：Gemini 图片生成 API + 文档转网页 + Nginx 静态文件服务
# 支持: CentOS 7/8/9, Ubuntu 20+, Debian 11+
#
# 用法:
#   bash install.sh --gemini-key YOUR_KEY
#   bash install.sh --gemini-key YOUR_KEY --port 1001 --api-port 1002
#   bash install.sh --gemini-key YOUR_KEY --public-base https://your-domain.com
# =============================================================================
set -e

# ── 默认参数 ──────────────────────────────────────────────────────────────────
STATIC_PORT=1001
API_PORT=1002
PUBLIC_BASE=""
GEMINI_KEY=""
INSTALL_DIR="/opt/media-hosting-suite"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)         STATIC_PORT="$2"; shift 2;;
    --api-port)     API_PORT="$2"; shift 2;;
    --public-base)  PUBLIC_BASE="$2"; shift 2;;
    --gemini-key)   GEMINI_KEY="$2"; shift 2;;
    *) shift;;
  esac
done

if [[ -z "$GEMINI_KEY" ]]; then
  echo "ERROR: 请提供 Gemini API Key: bash install.sh --gemini-key YOUR_KEY"
  exit 1
fi

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
if [ -z "$PUBLIC_BASE" ]; then
  PUBLIC_BASE="http://${SERVER_IP}:${STATIC_PORT}"
fi

echo "╔══════════════════════════════════════════╗"
echo "║   Media Hosting Suite — 安装开始         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  静态文件端口: $STATIC_PORT              ║"
echo "║  API 端口:     $API_PORT                 ║"
echo "║  公共域名:     $PUBLIC_BASE              ║"
echo "╚══════════════════════════════════════════╝"

# ── 检测系统 ──────────────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  PKG_MGR="apt"
  apt-get update -qq
elif command -v dnf &>/dev/null; then
  PKG_MGR="dnf"
  if ! rpm -q epel-release &>/dev/null; then
    dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm 2>/dev/null || \
    dnf install -y epel-release 2>/dev/null || true
  fi
elif command -v yum &>/dev/null; then
  PKG_MGR="yum"
fi

install_pkg() {
  if [ "$PKG_MGR" = "apt" ]; then
    apt-get install -y "$@"
  elif [ "$PKG_MGR" = "dnf" ]; then
    dnf install -y "$@" --skip-broken
  else
    yum install -y "$@"
  fi
}

echo ""
echo "══ Step 1/6  安装系统依赖 ══"
install_pkg nginx python3 python3-pip curl wget unzip \
  xorg-x11-server-Xvfb openbox x11vnc xdotool ImageMagick \
  poppler-utils 2>/dev/null || \
install_pkg nginx python3 python3-pip curl wget unzip \
  xvfb openbox x11vnc xdotool imagemagick poppler-utils 2>/dev/null || true

echo ""
echo "══ Step 2/4  安装 Python 依赖 ══"
pip3 install flask requests markdown python-docx 2>/dev/null || true

echo ""
echo "══ Step 3/4  部署项目文件 ══"
mkdir -p "$INSTALL_DIR/api" /var/www/images

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -f "$SCRIPT_DIR/../api/server.py" "$INSTALL_DIR/api/server.py"

# 写入环境变量（不提交到 git）
printf "GEMINI_API_KEY=%s\nPUBLIC_BASE=%s\n" "$GEMINI_KEY" "$PUBLIC_BASE" \
  > "$INSTALL_DIR/.env"

# 注入端口配置到 server.py（如果非默认）
if [ "$API_PORT" != "1002" ]; then
  sed -i "s/port=1002/port=$API_PORT/" "$INSTALL_DIR/api/server.py"
fi

# Nginx 配置
cat > /etc/nginx/conf.d/media-hosting.conf << NGEOF
server {
    listen $STATIC_PORT;
    server_name _;
    location / {
        root /var/www/images;
        autoindex on;
        add_header Access-Control-Allow-Origin *;
    }
}
NGEOF
nginx -t && systemctl enable nginx && systemctl restart nginx

cat > /etc/systemd/system/media-api.service << SVCEOF
[Unit]
Description=Media Hosting API
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/api
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=python3 $INSTALL_DIR/api/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

echo ""
echo "══ Step 4/4  启动服务 ══"
systemctl daemon-reload
systemctl enable media-api
systemctl restart media-api

echo -n "等待服务启动"
for i in $(seq 1 10); do
  echo -n "."
  sleep 1
  if curl -s "http://127.0.0.1:$API_PORT" -o /dev/null 2>/dev/null; then
    echo " OK"
    break
  fi
done

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   OK  Media Hosting Suite 部署成功！                 ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  静态文件:  http://${SERVER_IP}:${STATIC_PORT}/      ║"
echo "║  API:       http://${SERVER_IP}:${API_PORT}          ║"
echo "║  管理界面:  http://${SERVER_IP}:${API_PORT}/admin    ║"
echo "║                                                       ║"
echo "╚══════════════════════════════════════════════════════╝"
