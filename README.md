# Media Hosting Suite

> Gemini AI 图片生成 + 文档转网页 + noVNC 远程浏览器 — 三合一一键部署套件

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📦 项目结构

```
media-hosting-suite/
├── api/
│   ├── server.py          # Flask API 主服务（图片生成 + 文档转页面 + 管理界面）
│   └── requirements.txt   # Python 依赖
├── nginx/
│   └── images.conf        # Nginx 静态文件服务配置
├── systemd/
│   ├── media-api.service      # API 服务 systemd 单元
│   └── tunnel-agent.service   # Tunnel 代理 systemd 单元
├── scripts/
│   ├── install.sh                  # 一键安装脚本
│   └── remote-browser-watchdog.sh  # noVNC 守护进程
└── README.md
```

---

## 🚀 一键安装

```bash
# 基础安装（使用默认端口）
bash <(curl -fsSL https://raw.githubusercontent.com/divanoo65/media-hosting-suite/main/scripts/install.sh)

# 自定义端口和公共域名
bash <(curl -fsSL https://raw.githubusercontent.com/divanoo65/media-hosting-suite/main/scripts/install.sh) \
  --port 1001 \
  --api-port 1002 \
  --novnc-port 1006 \
  --public-base https://your-domain.com \
  --gemini-key YOUR_GEMINI_API_KEY
```

安装完成后会显示所有访问地址。

---

## 🧩 服务说明

### 服务架构

```
用户浏览器
    │
    ├── http://IP:1002/admin        ← 文件管理界面
    │
    ├── http://IP:1002/...          ← API 接口 (Flask)
    │       │
    │       └── 生成文件 → /var/www/images/
    │                           │
    ├── http://IP:1001/...  ← Nginx 静态服务
    │   (或公共域名)
    │
    └── http://IP:1006/vnc_lite.html  ← noVNC 远程浏览器
```

### 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| `1001` | Nginx | 静态文件服务，对外提供图片/HTML访问 |
| `1002` | Flask API | 图片生成 + 文档转页面 + 管理界面 |
| `1006` | noVNC | 远程浏览器桌面 |
| `5900` | VNC | x11vnc内部端口（websockify转发） |

---

## 📡 API 接口

### 1. 图片生成

与 Gemini API 完全兼容，自动将 base64 图片替换为公共 URL。

```http
POST http://IP:1002/v1beta/models/gemini-2.5-flash-image:generateContent
Content-Type: application/json

{
  "contents": [
    {"parts": [{"text": "一只在睡觉的橘猫，水彩画风格"}]}
  ]
}
```

**响应**（在标准 Gemini 响应基础上增加 `image_urls`）：
```json
{
  "candidates": [...],
  "image_urls": ["https://your-domain.com/abc123.png"]
}
```

### 2. 文档转网页

上传文档（.txt / .md / .pdf / .docx），AI 自动生成美观的 HTML 页面。

**方式一：文件上传**
```bash
curl -X POST http://IP:1002/v1beta/documents:toPage \
  -F "file=@report.pdf"
```

**方式二：直接传文本**
```bash
curl -X POST http://IP:1002/v1beta/documents:toPage \
  -H "Content-Type: application/json" \
  -d '{"title": "我的文档", "content": "# 标题\n\n内容..."}'
```

**响应：**
```json
{
  "page_url": "https://your-domain.com/def456.html",
  "title": "我的文档"
}
```

### 3. 健康检查

```http
GET http://IP:1002/health
```

---

## 🗂️ 文件管理界面

访问 `http://IP:1002/admin` 即可打开管理界面，支持：

- 📋 **查看所有文件**：图片预览、文件大小、创建时间
- 🔗 **直接访问**：点击文件名在新标签打开
- ⬆️ **上传文件**：直接上传图片或其他文件
- 🗑️ **删除文件**：一键删除不需要的文件

---

## 🖥️ 远程浏览器 (noVNC)

访问 `http://IP:1006/vnc_lite.html`，点击 **Connect** 即可看到远程 Chrome 桌面。

**常用命令：**
```bash
# 截图
DISPLAY=:1 import -window root /tmp/screenshot.jpg

# 打开指定网址
DISPLAY=:1 google-chrome --no-sandbox https://youtube.com &

# 查看服务状态
systemctl status remote-browser
```

---

## ⚙️ 配置文件

安装后可修改 `/opt/media-hosting-suite/.env`：

```env
GEMINI_API_KEY=your_api_key_here
PUBLIC_BASE=https://your-domain.com
```

修改后重启 API 服务：
```bash
systemctl restart media-api
```

---

## 🔧 服务管理

```bash
# 查看所有服务状态
systemctl status media-api remote-browser nginx

# 重启某个服务
systemctl restart media-api
systemctl restart remote-browser
systemctl restart nginx

# 查看日志
tail -f /var/log/media-api.log
tail -f /var/log/novnc.log
journalctl -u remote-browser -f
```

---

## 📋 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | CentOS 7/8/9 · Ubuntu 20+ · Debian 11+ |
| Python | 3.6+ |
| 内存 | 建议 2GB+（Chrome 需要） |
| 磁盘 | 建议 20GB+（存储生成文件） |
| 网络 | 需要能访问 Gemini API |

---

## 📄 License

MIT
