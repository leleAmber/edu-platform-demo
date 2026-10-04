# 部署到 Ubuntu 24.04（systemd + nginx）

面向 Ubuntu 24.04 LTS，用系统自带的 systemd 管进程、nginx 做唯一对外入口。
MySQL 走 apt 安装。全程不需要 Docker。

## 部署后长这样

```
                    ┌─ /      → Streamlit 网页版      :8501
浏览器 / 微信  ──→ nginx :80 ─┼─ /api/  → FastAPI 移动端后端   :8000
                    └─ /h5/  → 移动端 H5 静态文件（无进程）
                                        └─→ MySQL :3306（三个模块共用）
```

`streamlit` 与 `uvicorn` 都只监听 `127.0.0.1`，公网只能通过 nginx 访问。

**约定的路径**：代码放 `/srv/edu-platform`，运行用户 `keban`。改了的话，
`deploy/*.service` 和 `deploy/nginx-keban.conf` 里的路径要同步改。

---

## 想省事：跑 `bootstrap.sh`

下面第 1~8 步全自动做完，幂等、可重复执行：

```bash
# 服务器上以 root 执行
SERVER_IP=你的服务器公网IP ./deploy/bootstrap.sh
```

它额外替你做了几件手工容易漏的事：小内存机器自动加 2G swap（npm 构建会 OOM）、
自动生成数据库密码并同时写进 MySQL 和 `secrets.toml`、api 起不来直接打印 Traceback、
**探测公网 IP**（云服务器网卡上只有内网地址，直接用 `hostname -I` 会让 H5 白屏）。

跑完还剩两件手工事，脚本结尾会再提醒一次：填 `LLM_API_KEYS`、控制台放行 80 端口。

想分步理解、或者要自定义配置（比如改路径、加 systemd 之外的进程管理器），
就按下面的 1~8 步手工来。

---

## 1. 装系统依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx mysql-server

# Node 别用 apt 的（24.04 源里是 18，已 EOL），用 NodeSource 装 22
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

> 服务器在大陆的话，给 npm 换个国内源，否则第 8 步装前端依赖会很慢
> （`npm ci` 要装 250MB 左右的包）：
>
> ```bash
> sudo -u keban npm config set registry https://registry.npmmirror.com
> ```

验证：`python3 -V`（应为 3.12）、`node -v`（应为 v22）。

## 2. 建运行用户并把代码放到位

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin keban

sudo mkdir -p /srv/edu-platform
sudo chown keban:keban /srv/edu-platform

# 必须用浅克隆，见下方说明
sudo -u keban git clone --depth 1 --single-branch --branch release-python \
    https://github.com/leleAmber/edu-platform-demo.git /srv/edu-platform
```

> **为什么是浅克隆**：仓库历史里曾经提交过 7 份教材 PDF（合计约 230MB，现已从
> 工作区移除但仍留在历史中），完整 `git clone` 要拉 **215MB**。当前代码快照本身
> 只有 **14.8MB**，`--depth 1` 只拉最新一版，**能省掉 93% 的流量和时间**。
>
> 这对境外的服务器无所谓，但对**大陆的机器几乎是必须的**——从 GitHub 拉 215MB
> 经常慢到超时。浅克隆下 `git pull --ff-only`（`update.sh` 用的）照常工作。

## 3. 建数据库和账号

```bash
sudo mysql <<'SQL'
CREATE DATABASE IF NOT EXISTS keban_ai
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 应用账号只给业务权限，不用 root 跑应用
CREATE USER IF NOT EXISTS 'keban_app'@'localhost' IDENTIFIED BY '换成强密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON keban_ai.* TO 'keban_app'@'localhost';
FLUSH PRIVILEGES;
SQL
```

表结构不用手工建，应用启动时自动 `CREATE TABLE IF NOT EXISTS`
（也可以手工执行仓库根的 `schema.sql`）。

> **关于密码认证**：MySQL 8 默认 `caching_sha2_password`。PyMySQL 在认证缓存
> 未命中时需要 `cryptography` 才能完成握手，否则报一个很难懂的错。项目已在
> `api/requirements.txt` 里声明该依赖，第 4 步会自动装上。

## 4. 建虚拟环境、装依赖

```bash
cd /srv/edu-platform
sudo -u keban python3 -m venv .venv
sudo -u keban .venv/bin/pip install -r requirements.txt -r api/requirements.txt
```

网页版和 api **共用这一个 venv**（api 没有独立虚拟环境）。

## 5. 放配置文件（最容易漏的一步）

### 5.1 `.streamlit/secrets.toml`

这个文件**被 `.gitignore` 忽略，不会随 git 下来**，必须在服务器上手工创建：

```bash
sudo -u keban mkdir -p /srv/edu-platform/.streamlit
sudo -u keban nano /srv/edu-platform/.streamlit/secrets.toml
```

内容参考仓库 README 的「第 2 步：填写连接信息」，至少要配：

```toml
DB_HOST = '127.0.0.1'
DB_PORT = '3306'
DB_USER = 'keban_app'
DB_PASSWORD = '第 3 步设的密码'
DB_NAME = 'keban_ai'
DB_SEED_DEMO = '0'                 # 测试阶段想用 student/admin 演示账号就设 '1'

AUTH_OTP_SECRET = '用 openssl rand -hex 32 生成'

LLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
LLM_MODEL = 'glm-4.7'
LLM_API_KEYS = ['key1', 'key2']

# 邮箱验证码注册需要，暂时不做注册可留空
SMTP_HOST = 'smtp.163.com'
SMTP_PORT = '465'
SMTP_USE_SSL = '1'
SMTP_LOGIN = '你的发件邮箱'
SMTP_PASSWORD = '邮箱授权码'
SMTP_SENDER_EMAIL = '你的发件邮箱'
```

```bash
sudo -u keban chmod 600 /srv/edu-platform/.streamlit/secrets.toml
```

> `secrets.toml` 同时被网页版和 api 读取（api 通过仓库根的 `core/` 定位到它），
> 所以**只配这一份**，不要在 api 里重复配数据库。

### 5.2 `api/.env`

```bash
sudo -u keban cp /srv/edu-platform/deploy/api.env.example /srv/edu-platform/api/.env
sudo -u keban nano /srv/edu-platform/api/.env
```

至少设 `API_JWT_SECRET`（`python3 -c "import secrets;print(secrets.token_urlsafe(48))"`）。

## 6. 装 systemd 服务

```bash
cd /srv/edu-platform
sudo cp deploy/keban-web.service deploy/keban-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now keban-web keban-api

# 看状态和日志
sudo systemctl status keban-web keban-api
sudo journalctl -u keban-api -f
```

到这里先确认两个服务单独能起来（还没配 nginx）：

```bash
curl -s localhost:8000/health       # 期望 {"ok":true,...}
curl -s -o /dev/null -w '%{http_code}\n' localhost:8501/   # 期望 200
```

## 7. 配 nginx

```bash
sudo cp /srv/edu-platform/deploy/nginx-keban.conf /etc/nginx/sites-available/keban
sudo ln -sf /etc/nginx/sites-available/keban /etc/nginx/sites-enabled/keban
sudo rm -f /etc/nginx/sites-enabled/default     # 去掉默认站点，否则会抢 80
sudo nginx -t && sudo systemctl reload nginx
```

## 8. 构建移动端 H5

```bash
cd /srv/edu-platform
sudo PUBLIC_ORIGIN=http://你的服务器IP ./deploy/update.sh
```

`update.sh` 做了：拉代码 → 装依赖 → 用 `VITE_API_BASE=<origin>/api` 构建 H5 →
检查 `secrets.toml` → 重启两个服务。

> **H5 的 API 地址是构建时写死的**。以后换了域名或 IP，必须重跑 `update.sh`
> 重新构建，只重启服务不生效。

## 9. 验收

| 检查 | 地址 | 期望 |
| --- | --- | --- |
| 网页版 | `http://IP/` | 出现登录页，`student / 123456` 能登录 |
| API 文档 | `http://IP/api/docs` | Swagger 页面 |
| API 健康 | `http://IP/api/health` | `{"ok":true,...}` |
| 移动端 H5 | `http://IP/h5/` | 手机浏览器打开，登录后各页面正常 |

---

## 日常更新

**在你自己电脑上跑**（不是服务器上），一条命令完成推代码 + 部署 + 从公网验收：

```bash
./deploy/release.sh            # 全量：推代码 → 装依赖 → 重建 H5 → 重启 → 验收
./deploy/release.sh --fast     # 只改了 Python 后端：跳过 apt 与 H5 构建
```

**什么时候不能用 `--fast`**：改了 `mobile/` 下任何前端代码，或者换了域名 / IP ——
H5 的 API 地址是构建时写死的，必须重新构建。脚本结尾会自己发现这一点并提示。

服务器上直接跑（比如你 ssh 进去手动操作）也可以：

```bash
cd /srv/edu-platform
sudo PUBLIC_ORIGIN=http://你的地址 ./deploy/update.sh
```

> **注意本项目的实际部署方式**：某些大陆节点（例如本机在用的腾讯云轻量深圳）
> 拉 GitHub 是完全不通的，那种情况下代码是用 `rsync` 推的，**服务器上没有 `.git`**，
> `update.sh` 里的 `git pull` 会被自动跳过。详见下面「数据同步」一节的说明。

---

## 数据同步（把本机开发数据搬到服务器）

服务器刚部署好时是个**空库**——应用会自动建表，但只有种子账号，没有题库等内容数据。
所以首次上线后必须跑一次：

```bash
./deploy/sync-data.sh --dry-run   # 先看看会同步哪些表、各多少行
./deploy/sync-data.sh             # 确认后执行
```

它做的事：本机 `mysqldump` → 压缩传到服务器 → 用 **root** 导入（应用账号 `keban_app`
的授权里没有 DROP，带 `DROP TABLE` 的全量 dump 用它导入会失败）→ 重启服务 →
逐表比对两边行数。**这是覆盖式同步**：服务器上同名表的现有数据会先被 DROP 掉。

### 用户账号不会被删

默认**保留服务器上独有的账号**：线上随时可能有人注册，全量覆盖会把他们删掉，而且不可逆。
脚本会在导入前把服务器的 `users` 表备份到临时表，导入后把本机没有的账号补回去
（靠 `username` 唯一键去重，同名以本机为准）。执行前它会先把这些账号列出来给你看。

只有明确要让「服务器上的用户也以本机为准」时才加 `--replace-users`：

```bash
./deploy/sync-data.sh --replace-users --yes    # 危险：服务器独有账号会永久丢失
```

## 排错

**网页版一直转圈 / 界面不动** —— nginx 的 WebSocket 头没配。检查
`location /` 里的 `Upgrade` / `Connection` 两行（本仓库的配置已含）。

**Streamlit 报 `Connection error` 或 XSRF 报错** —— 反代没透传 Host。
确认 `proxy_set_header Host $host;` 存在。仍不行再给 Streamlit 加
`--server.enableCORS=false --server.enableXsrfProtection=false`
（仅在没有其他反代层时用）。

**api 启动就报找不到 core/** —— 工作目录不对。`keban-api.service` 里
`WorkingDirectory` 必须是 `/srv/edu-platform/api`，`core/` 在其上一级。

**连不上数据库** —— 用具体原因定位，别猜：

```bash
cd /srv/edu-platform
sudo -u keban .venv/bin/python -c "from core import database; print(database.health_check())"
```

`Access denied` 是密码不对，`Can't connect` 是 MySQL 没起或端口不通，
`Unknown database` 是库没建。

**H5 打开是白屏 / 请求 404** —— 多半是构建时的 `VITE_API_BASE` 不对。
确认 `update.sh` 跑的时候 `PUBLIC_ORIGIN` 是**用户浏览器能访问到的地址**
（不是 `localhost`），然后重新构建。

---

## 上线小程序时（现在不用做）

小程序不在服务器上部署，代码传微信平台，它只调你的 API。但要求：

1. 有**已备案的域名**（ICP 备案，周期以周计，早点启动）。
2. 配 HTTPS 证书（`certbot --nginx -d your-domain.com` 最省事）。
3. 微信公众平台 → 开发管理 → 开发设置 → 服务器域名，把 `https://your-domain.com`
   加入 `request` 合法域名。
4. 填 `mobile/src/manifest.json` 的 `mp-weixin.appid`。
5. 构建：`VITE_API_BASE=https://your-domain.com/api npm run build:mp-weixin`，
   产物在 `mobile/dist/build/mp-weixin`，用微信开发者工具导入上传。
