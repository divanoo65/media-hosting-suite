---
name: domain-bootstrap
description: >
  为新项目一键完成公网域名接入：注册域名、安装/启动 agent、支持用户指定固定域名并冲突重试。
---

# Domain Bootstrap Skill

用于把一个本地服务（如 `127.0.0.1:3000`）从零到一接入公网。

## 能力

- 自动注册初始公网域名（随机后缀）
- 生成并执行 agent 安装/启动命令
- 支持用户不满意自动域名时，改绑自定义域名
- 域名冲突（409）时提示并继续询问新域名

## 典型输入

- `给 myapp 3000 端口开通公网域名`
- `给 1003 服务分配域名，并安装 agent`
- `给项目分配域名，我希望是 api.example.com`

## 关键接口

- `POST https://domain.vyibc.com/api/sessions/register`
- `POST https://domain.vyibc.com/api/routes`

## 输出要求

- 返回最终公网地址
- 返回 Tunnel ID / Token
- 返回可直接执行的 agent 启动命令
- 说明是否成功绑定了用户指定域名

