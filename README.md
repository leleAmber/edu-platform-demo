# 课伴AI｜英语课本智能学习助手

基于 Streamlit 和 Python 的英语课本学习助手原型。`index.html` 保留为交互与视觉参考，当前可运行应用入口为 `app.py`。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

应用默认使用 `data/edu_platform.db` 保存用户、验证码、会员订单、客服留言和学习记录。该运行数据库已加入 Git 忽略规则。

## 演示账号

- 学生：`student / 123456`
- 管理员：`admin / 123456`

首次启动时会创建演示账号。部署到生产环境前，请禁用或更换这些账号，并改用受控的用户初始化流程。

## 邮箱验证码

验证码通过项目已有的 `.streamlit/secrets.toml` 配置发送。应用读取以下字段：

- `AUTH_OTP_SECRET`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USE_SSL`
- `SMTP_LOGIN`
- `SMTP_PASSWORD`
- `SMTP_SENDER_EMAIL`
- `AUTH_DEV_MODE`（可选，设为 `1` 时只用于本地演示并在页面显示验证码）

验证码 10 分钟过期、每个邮箱 60 秒最多发送一次，最多校验 5 次，成功后立即失效。不要将 secrets 提交到 Git。

## 功能范围

- 登录、邮箱验证码注册、管理员与普通用户角色
- 课本预习、单元复习、作业反馈与学习记录
- VIP 演示权益、模拟支付、客服留言及管理员后台
- SQLite 持久化和 PBKDF2-SHA256 密码哈希

AI 批改、学习内容、会员支付目前属于原型演示。真实上线还需接入正版教材、AI 服务、支付商户后端及更完善的账号风控与会话管理。
