#!/bin/bash
# =============================================================================
# Media Hosting Suite — 一键安装脚本
# 支持: CentOS 7/8/9, Ubuntu 20+, Debian 11+
# 用法: bash install.sh [--port 1001] [--api-port 1002] [--novnc-port 1006]
#        [--public-base https://your-domain.com] [--gemini-key YOUR_KEY]
# =============================================================================
set -e

# ── 默认参数 ──────────────────────────────────────────────────────────────────
STATIC_PORT=1001
API_PORT=1002
NOVNC_PORT=1006
PUBLIC_BASE=""
GEMINI_KEY="AIzaSyBLhPHdw7SSgiTM5wJZLzPyX1kmAZEpGI0"
INSTALL_DIR="/opt/media-hosting-suite"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)         STATIC_PORT="$2"; shift 2;;
    --api-port)     API_PORT="$2"; shift 2;;
    --novnc-port)   NOVNC_PORT="$2"; shift 2;;
    --public-base)  PUBLIC_BASE="$2"; shift 2;;
    --gemini-key)   GEMINI_KEY="$2"; shift 2;;
    *) shift;;
  esac
done

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
if [ -z "$PUBLIC_BASE" ]; then
  PUBLIC_BASE="http://${SERVER_IP}:${STATIC_PORT}"
fi

echo "╔══════════════════════════════════════════╗"
echo "║   Media Hosting Suite — 安装开始         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  静态文件端口: $STATIC_PORT"
echo "║  API 端口:     $API_PORT"
echo "║  noVNC 端口:   $NOVNC_PORT"
echo "║  公共域名:     $PUBLIC_BASE"
echo "╚══════════════════════════════════════════╝"

# ── 检测系统 ──────────────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  PKG_MGR="apt"
  apt-get update -qq
elif command -v dnf &>/dev/null; then
  PKG_MGR="dnf"
  # CentOS Stream 9: disable broken repos if needed
  dnf config-manager --set-disabled powertools 2>/dev/null || true
  dnf config-manager --set-disabled crb 2>/dev/null || true
  # Enable EPEL
  if ! rpm -q epel-release &>/dev/null; then
    EPEL_URL="https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm"
    dnf install -y "$EPEL_URL" 2>/dev/null || dnf install -y epel-release 2>/dev/null || true
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
echo "══ Step 2/6  安装 websockify + noVNC ══"
pip3 install websockify 2>/dev/null || true
mkdir -p /usr/share/novnc
if [ ! -f /usr/share/novnc/vnc_lite.html ]; then
  curl -fsSL https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz | tar -xz -C /tmp
  cp -r /tmp/noVNC-1.4.0/* /usr/share/novnc/
fi

echo ""
echo "══ Step 3/6  安装 Google Chrome ══"
if ! command -v google-chrome &>/dev/null; then
  if [ "$PKG_MGR" = "apt" ]; then
    wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    apt-get install -y /tmp/chrome.deb || true
  else
    cat > /etc/yum.repos.d/google-chrome.repo << 'REPO'
[google-chrome]
name=google-chrome
baseurl=http://dl.google.com/linux/chrome/rpm/stable/x86_64
enabled=1
gpgcheck=1
gpgkey=https://dl.google.com/linux/linux_signing_key.pub
REPO
    install_pkg google-chrome-stable
  fi
fi

echo ""
echo "══ Step 4/6  安装 Python 依赖 ══"
pip3 install flask requests markdown python-docx 2>/dev/null || true

echo ""
echo "══ Step 5/6  部署项目文件 ══"
mkdir -p "$INSTALL_DIR/api" /var/www/images

# 复制 API 服务
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -f "$SCRIPT_DIR/../api/server.py" "$INSTALL_DIR/api/server.py"

# 写入环境变量
cat > "$INSTALL_DIR/.env" << ENVEOF
GEMINI_API_KEY=$GEMINI_KEY
PUBLIC_BASE=$PUBLIC_BASE
ENVEOF

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

# Watchdog 脚本
cp -f "$SCRIPT_DIR/remote-browser-watchdog.sh" /usr/local/bin/remote-browser-watchdog.sh
chmod +x /usr/local/bin/remote-browser-watchdog.sh

# Systemd 服务
sed "s|1002|$API_PORT|g" "$SCRIPT_DIR/../systemd/media-api.service" \
  > /etc/systemd/system/media-api.service

cat > /etc/systemd/system/remote-browser.service << SVCEOF
[Unit]
Description=Remote Browser (Xvfb + Chrome + noVNC)
After=network.target

[Service]
Type=simple
Environment=NOVNC_PORT=$NOVNC_PORT
ExecStart=/usr/local/bin/remote-browser-watchdog.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

echo ""
echo "══ Step 6/6  启动所有服务 ══"
systemctl daemon-reload
systemctl enable media-api remote-browser
systemctl restart media-api
systemctl restart remote-browser

# 等待服务就绪
echo -n "等待服务启动"
for i in $(seq 1 12); do
  echo -n "."
  sleep 1
  if ss -tlnp | grep -q ":$API_PORT" && ss -tlnp | grep -q ":$NOVNC_PORT"; then
    echo ""
    break
  fi
done

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅  Media Hosting Suite 部署成功！                 ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  📁  静态文件访问:                                    ║"
echo "║      http://${SERVER_IP}:${STATIC_PORT}/             ║"
echo "║                                                       ║"
echo "║  🔌  API 接口 (图片生成 / 文档转页面):               ║"
echo "║      http://${SERVER_IP}:${API_PORT}                 ║"
echo "║                                                       ║"
echo "║  🗂️   文件管理界面:                                   ║"
echo "║      http://${SERVER_IP}:${API_PORT}/admin           ║"
echo "║                                                       ║"
echo "║  🖥️   远程浏览器 (noVNC):                            ║"
echo "║      http://${SERVER_IP}:${NOVNC_PORT}/vnc_lite.html ║"
echo "╚══════════════════════════════════════════════════════╝"
