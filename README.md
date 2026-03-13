# VYIBC Unified Stack

统一管理 1001/1002/1003 服务，支持一键部署、开机自启、自动重启、自动注册/绑定域名与 agent 启动。

## 包含内容

- `image-api/`：1002 Flask 服务（图片生成 + 文档转页面）
- `nginx/`：1001 与 1003 静态文件服务配置
- `docker-compose.yml`：统一编排（1002 Docker 化）
- `nginx/images.conf`：1001/1003 主机 Nginx 配置（由部署脚本下发）
- `systemd/vyibc-stack.service`：开机自动拉起 compose
- `scripts/register_domains.sh`：下载 agent、注册域名、绑定固定域名、启动 agent systemd
- `scripts/one_click_deploy.sh`：一键部署
- `skills/domain-bootstrap/`：新项目域名开通 Skill（自动注册 + 可自定义域名 + agent 安装启动）

## 预设固定域名

- `skill.vyibc.com -> 1001`
- `skills.vyibc.com -> 1001`
- `images.vyibc.com -> 1002`
- `resource.vyibc.com -> 1002`

## 使用

```bash
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env，填写 GEMINI_API_KEY
bash scripts/one_click_deploy.sh
```

## 说明

- 脚本不会把 PAT 或 API Key 写入仓库。
- 若固定域名已被他人占用，脚本会提示冲突并保留自动生成域名。
