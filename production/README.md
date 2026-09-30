# 课伴AI正式版

`../index.html` 是原型文件，保持原样不参与正式版运行。正式版全部代码在本目录，启动后访问 `http://localhost:3000`。

## 技术选型

- Node.js 24+：使用内置 `node:sqlite`，单服务部署，适合 Render、Railway、Fly.io、VPS 等低成本平台。
- Express：接口和静态资源放在同一个进程，减少部署组件。
- Node 24 内置 SQLite（`node:sqlite`）：不需要编译原生扩展，单机和小规模产品成本低，后续可迁移到 PostgreSQL。
- SMTP（Nodemailer）：邮件服务可替换为任意 SMTP 提供商。
- Stripe Checkout：用托管收银台减少支付页面和卡信息合规工作；未配置密钥时仅提供本地测试支付。

## 本地启动

```bash
cd edu-platform-demo/production
cp .env.example .env
npm install
npm start
```

首次启动会自动创建 SQLite 数据库和 `.env` 中的管理员账号。不要把 `.env` 或 `data/` 提交到代码仓库。

## 需要替换的信息

1. **管理员账号**：修改 `.env` 的 `ADMIN_USERNAME`、`ADMIN_EMAIL`、`ADMIN_PASSWORD`。首次启动前修改最安全；已经启动过的账号请直接在数据库或后续管理功能中修改。
2. **邮箱验证/找回密码**：配置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_SECURE`、`SMTP_USER`、`SMTP_PASS`、`MAIL_FROM`。生产环境把 `ALLOW_DEV_EMAIL_CODE=false`，否则未配置 SMTP 时不会发送真实邮件。
3. **支付**：在 Stripe Dashboard 创建 API Key，把 `STRIPE_SECRET_KEY` 写入 `.env`，并创建 webhook endpoint `POST /api/webhooks/stripe`，事件至少勾选 `checkout.session.completed`，将签名密钥写入 `STRIPE_WEBHOOK_SECRET`。`APP_URL`、成功和取消回跳地址也要改成正式域名。
4. **部署安全**：正式环境使用 HTTPS，并设置 `COOKIE_SECURE=true`、`NODE_ENV=production`。数据库文件应放在持久化磁盘；无持久化磁盘的平台不适合直接使用 SQLite。

## 已实现接口

- `POST /api/auth/register` 注册并发送邮箱验证码
- `POST /api/auth/verify-email` 验证邮箱并建立会话
- `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- `POST /api/auth/forgot-password`、`POST /api/auth/reset-password`、`POST /api/auth/change-password`
- `POST /api/payments/checkout` 创建 Stripe Checkout 或本地测试订单
- `POST /api/webhooks/stripe` 支付回调，幂等开通会员
- `GET /api/orders`、`POST /api/support/messages`、学习记录接口
- 管理员用户、订单、客服留言查询与回复接口

开发环境未配置 SMTP 时，注册接口会返回 `devCode`，忘记密码接口会返回 `devResetToken`；正式环境不会返回这些字段。
