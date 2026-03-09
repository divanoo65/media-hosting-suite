---
name: start-media-suite
description: >
  当用户说"启动媒体套件"、"start media suite"、"启动图片服务"、
  "重启图片生成服务"、"media hosting 启动"、"一键启动项目" 时自动触发。
  一键启动 Media Hosting Suite 的全部服务（Nginx + API + 隧道代理）。
---

# 一键启动 Media Hosting Suite

**一句话启动所有服务，自动检查并修复未运行的服务。**

## 使用场景

- 服务器重启后需要重新启动所有服务
- 某个服务异常退出需要恢复
- 首次部署完成后一键启动
- 快速检查所有服务状态

## 用法示例

```
启动媒体套件
start media suite
重启图片生成服务
一键启动项目
```

## 包含服务

| 服务 | 端口 | 说明 |
|------|------|------|
| nginx | 1001 | 静态文件服务，提供公网图片访问 |
| image-api | 1002 | Flask API：图片生成 + 文档转网页 + 管理界面 |
| images-tunnel | — | 隧道代理，将 nginx 映射到公网域名 |

## 服务地址

- **API**: `http://127.0.0.1:1002`
- **管理界面**: `http://127.0.0.1:1002/admin`
- **公网图片**: 见 `/opt/image-api/.env` 中的 `PUBLIC_BASE`

## 工作流程

```
用户说：启动媒体套件
      ↓
1. 执行 bash /path/to/start.sh
   或依次运行:
   systemctl start nginx
   systemctl start image-api
   systemctl start images-tunnel
2. 检查每个服务的 active 状态
3. 报告结果，失败的给出排查命令
```

## 手动启动命令

```bash
# 一键启动（推荐）
bash /opt/media-hosting-suite/scripts/start.sh

# 或逐个启动
systemctl start nginx
systemctl start image-api
systemctl start images-tunnel

# 查看状态
systemctl status nginx image-api images-tunnel

# 查看日志
journalctl -u image-api -n 50
journalctl -u images-tunnel -n 50
```

## 触发关键词

- "启动媒体套件"
- "start media suite"
- "启动图片服务"
- "重启图片生成服务"
- "media hosting 启动"
- "一键启动项目"
- "服务挂了帮我重启"
