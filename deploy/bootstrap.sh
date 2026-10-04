#!/usr/bin/env bash
#
# 课伴AI 一键部署（Ubuntu 24.04，systemd + nginx，无 Docker）
#
# 一次装好三个模块：网页版 Streamlit(:8501) / 移动端后端 FastAPI(:8000) / H5 静态文件，
# 由 nginx :80 收口。详细说明见 deploy/README.md。
#
# 用法（服务器上以 root 执行）：
#   ./deploy/bootstrap.sh                              # 对外地址自动取本机第一个 IP
#   SERVER_IP=111.231.10.101 ./deploy/bootstrap.sh     # 显式指定
#   SKIP_APT=1 ./deploy/bootstrap.sh                   # 系统依赖已装好，跳过 apt
#   SKIP_H5=1  ./deploy/bootstrap.sh                   # 先不构建 H5（省 3~5 分钟）
#
# 幂等：可重复执行。已存在的用户 / 库 / secrets.toml / 服务都不会被覆盖，
#       只有代码会用 git pull 或 rsync 更新一次。
#
# 跑完还有两件手工事：填大模型 key、确认轻量控制台放行了 80 端口 —— 见结尾提示。
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/edu-platform}"
APP_USER="${APP_USER:-keban}"
DB_NAME="${DB_NAME:-keban_ai}"
DB_USER="${DB_USER:-keban_app}"
REPO_URL="${REPO_URL:-https://github.com/leleAmber/edu-platform-demo.git}"
BRANCH="${BRANCH:-release-python}"
SERVER_IP="${SERVER_IP:-}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_H5="${SKIP_H5:-0}"
# 大陆机器直连 PyPI 装 150MB 轮子经常超时，默认走清华源；想用官方源设 PIP_INDEX=https://pypi.org/simple
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m!!  %s\033[0m\n' "$*" >&2; exit 1; }

is_private_ip() {
    [[ "$1" =~ ^(10\.|127\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.) ]]
}

# 云服务器（含腾讯云轻量）的网卡上只有内网 IP，公网 IP 是平台 NAT 的。
# 所以 hostname -I 拿到的地址**不能**当对外地址用——写进 H5 就是白屏。
detect_public_ip() {
    local ip
    for url in https://api.ipify.org https://ifconfig.me/ip https://ipinfo.io/ip; do
        ip="$(curl -fsS --max-time 5 "$url" 2>/dev/null | tr -d '[:space:]')" || continue
        [[ "$ip" =~ ^[0-9]+(\.[0-9]+){3}$ ]] && { printf '%s' "$ip"; return 0; }
    done
    return 1
}

# --------------------------------------------------------------------------- #
# 0. 预检：root / 系统版本 / Python / 内存
# --------------------------------------------------------------------------- #
log "0/8 环境预检"
[[ $EUID -eq 0 ]] || die "请用 root 运行：sudo -i 后执行，或 sudo ./deploy/bootstrap.sh"

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${VERSION_ID:-}" != "24.04" ]]; then
    warn "当前系统是 ${PRETTY_NAME:-未知}，本项目按 Ubuntu 24.04 + Python 3.12 验证。"
    warn "轻量应用服务器可在控制台「重装系统」换 Ubuntu 24.04，现在还没数据，成本最低。"
fi

if ! command -v python3 >/dev/null; then
    die "没有 python3。先跑：apt update && apt install -y python3 python3-venv"
fi
PY_VER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if [[ "$(printf '%s\n3.12\n' "$PY_VER" | sort -V | head -1)" != "3.12" ]]; then
    die "Python 是 ${PY_VER}，需要 >= 3.12（装出来的是 3.10 说明系统是 22.04，请重装为 24.04）。"
fi
echo "    Python $PY_VER"

# npm 构建前端峰值要吃 1G+，小内存机器先加 swap，否则会被 OOM 杀掉
MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
SWAP_MB=$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo)
echo "    内存 ${MEM_MB}MB，swap ${SWAP_MB}MB"
if (( MEM_MB < 3000 && SWAP_MB < 1024 )); then
    log "内存偏小，加 2G swap"
    fallocate -l 2G /swapfile 2>/dev/null \
        || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    chmod 600 /swapfile
    mkswap -q /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "    已启用 /swapfile（写入 /etc/fstab，重启后仍在）"
fi

# --------------------------------------------------------------------------- #
# 1. 系统依赖
# --------------------------------------------------------------------------- #
if [[ "$SKIP_APT" == 1 ]]; then
    log "1/8 跳过系统依赖（SKIP_APT=1）"
else
    log "1/8 安装系统依赖"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3-venv python3-pip git nginx mysql-server rsync openssl

    # Node 不用 apt 的（24.04 源里是 18，已 EOL），用 NodeSource 装 22
    NODE_MAJOR="$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || true)"
    NODE_MAJOR="${NODE_MAJOR:-0}"
    if (( NODE_MAJOR < 20 )); then
        echo "    安装 Node 22（当前：$(node -v 2>/dev/null || echo 无)）"
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
        apt-get install -y -qq nodejs
    fi
    echo "    $(python3 -V) / node $(node -v)"
fi

# --------------------------------------------------------------------------- #
# 2. 运行用户 + 代码
# --------------------------------------------------------------------------- #
log "2/8 准备运行用户与代码"
id -u "$APP_USER" >/dev/null 2>&1 \
    || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"

# 本脚本在仓库的 deploy/ 下，上一级即仓库根
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE="$(dirname "$SCRIPT_DIR")"

if [[ -f "$APP_DIR/app.py" ]]; then
    if [[ -d "$APP_DIR/.git" ]]; then
        echo "    已有代码，git pull 更新"
        sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
    elif [[ -f "$HERE/app.py" && "$HERE" != "$APP_DIR" ]]; then
        # 本机跑 release.sh 时，代码先 rsync 到暂存目录（/tmp/edu-platform），再由
        # 本脚本部署——所以这里必须把暂存目录的代码同步过来。**不能跳过**：这台
        # 服务器没有 .git（拉不动 GitHub），跳过的话发版会「成功」但服务器跑的还是旧代码。
        echo "    无 .git（rsync 部署）：从 $HERE 同步代码到 $APP_DIR"
        rsync -a --exclude 'venv' --exclude '.venv' --exclude 'node_modules' \
                  --exclude '__pycache__' --exclude 'mobile/dist' \
                  --exclude '.streamlit/secrets.toml' \
                  "$HERE"/ "$APP_DIR"/
    else
        echo "    已有代码（无 .git 且不在暂存目录），跳过更新"
    fi
elif [[ -f "$HERE/app.py" && "$HERE" != "$APP_DIR" ]]; then
    # 代码是 rsync/scp 上来的：直接搬进去，绕开大陆拉 GitHub 慢的问题
    echo "    从 $HERE 复制代码到 $APP_DIR"
    rsync -a --exclude 'venv' --exclude '.venv' --exclude 'node_modules' \
              --exclude '__pycache__' --exclude 'mobile/dist' \
              --exclude '.streamlit/secrets.toml' \
              "$HERE"/ "$APP_DIR"/
else
    echo "    从 GitHub 浅克隆（--depth 1，只需 ~15MB）"
    sudo -u "$APP_USER" git clone --depth 1 --single-branch --branch "$BRANCH" \
        "$REPO_URL" "$APP_DIR" \
        || die "clone 失败（大陆机器常见）。改法：在本机 rsync 整个仓库到 ${APP_DIR}，再重跑本脚本。"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --------------------------------------------------------------------------- #
# 3. 数据库 + 应用账号
# --------------------------------------------------------------------------- #
log "3/8 建数据库与应用账号"
SECRETS="$APP_DIR/.streamlit/secrets.toml"
mkdir -p "$APP_DIR/.streamlit"

# 密码以 secrets.toml 为准：已存在就复用，保证 MySQL 里的密码和配置永远一致
if [[ -f "$SECRETS" ]] && grep -q '^DB_PASSWORD' "$SECRETS"; then
    DB_PASSWORD="$(grep -m1 '^DB_PASSWORD' "$SECRETS" \
        | sed -E "s/.*=[[:space:]]*['\"]([^'\"]*)['\"].*/\1/")"
    echo "    复用 secrets.toml 里已有的数据库密码"
else
    # 去掉 / + = 只留字母数字，避免拼进 SQL 时踩转义
    DB_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-24)"
    echo "    已生成数据库密码（写入 secrets.toml）"
fi

mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "    库 $DB_NAME / 账号 $DB_USER 就绪（表结构由应用启动时自动创建）"

# --------------------------------------------------------------------------- #
# 4. 虚拟环境
# --------------------------------------------------------------------------- #
log "4/8 安装 Python 依赖（网页版与 api 共用一个 venv）"
[[ -d "$APP_DIR/.venv" ]] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
echo "    使用源：$PIP_INDEX"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -i "$PIP_INDEX" \
    -r "$APP_DIR/requirements.txt" -r "$APP_DIR/api/requirements.txt"

# --------------------------------------------------------------------------- #
# 5. 配置文件（被 .gitignore 忽略，不会随 git 下来）
# --------------------------------------------------------------------------- #
log "5/8 写配置文件"
if [[ -f "$SECRETS" ]]; then
    echo "    secrets.toml 已存在，保留不动"
else
    OTP_SECRET="$(openssl rand -hex 32)"
    cat > "$SECRETS" <<EOF
# 课伴AI 配置（由 deploy/bootstrap.sh 生成于 $(date +%F)）
#
# 这份文件同时被网页版和 api 读取，**只配这一份**。
# 唯一必须手工补的是下面的 LLM_API_KEYS —— 留空应用能跑，但大模型批改会退回本地规则引擎。

# —— 数据库（已自动配好）——
DB_HOST = '127.0.0.1'
DB_PORT = '3306'
DB_USER = '$DB_USER'
DB_PASSWORD = '$DB_PASSWORD'
DB_NAME = '$DB_NAME'
# users 表为空时写入演示账号（student / admin）。不想要演示数据就改成 '0'
DB_SEED_DEMO = '1'

# —— 登录凭证签名（已自动生成随机值）——
AUTH_OTP_SECRET = '$OTP_SECRET'

# —— 大模型：智谱 glm-4.7，双 key 池，缺一个也能跑 ——
LLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
LLM_MODEL = 'glm-4.7'
# 移动端作业拍照批改走视觉模型
LLM_VISION_MODEL = 'glm-4v-flash'
LLM_API_KEYS = [
    # '把第一把 key 填这里',
    # '把第二把 key 填这里',
]

# —— 邮箱验证码注册（留空则不启用注册邮件，其他功能不受影响）——
SMTP_HOST = ''
SMTP_PORT = '465'
SMTP_USE_SSL = '1'
SMTP_LOGIN = ''
SMTP_PASSWORD = ''
SMTP_SENDER_EMAIL = ''
EOF
    chown "$APP_USER:$APP_USER" "$SECRETS"
    chmod 600 "$SECRETS"
    echo "    已生成 $SECRETS"
fi

# api 独有的配置（数据库与大模型不在这里，api 会去读上面那份 secrets.toml）
if [[ -f "$APP_DIR/api/.env" ]]; then
    echo "    api/.env 已存在，保留不动"
else
    cat > "$APP_DIR/api/.env" <<EOF
# 移动端后端独有配置（由 deploy/bootstrap.sh 生成）
# 独立于 AUTH_OTP_SECRET：以后轮换 OTP 密钥时不会把所有已登录用户踢下线。
API_JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
API_TOKEN_TTL_HOURS=168
EOF
    chown "$APP_USER:$APP_USER" "$APP_DIR/api/.env"
    chmod 600 "$APP_DIR/api/.env"
    echo "    已生成 $APP_DIR/api/.env"
fi

# --------------------------------------------------------------------------- #
# 6. systemd 服务
# --------------------------------------------------------------------------- #
log "6/8 安装并启动 systemd 服务"
cp "$APP_DIR/deploy/keban-web.service" "$APP_DIR/deploy/keban-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable keban-web keban-api >/dev/null 2>&1 || true
systemctl restart keban-web keban-api
echo "    等待 api 起来..."
API_OK=0
for _ in $(seq 1 20); do
    if curl -fsS --max-time 3 localhost:8000/health >/dev/null 2>&1; then API_OK=1; break; fi
    sleep 2
done
if (( API_OK )); then
    echo "    api 健康检查通过：$(curl -fsS localhost:8000/health)"
else
    warn "api 20 次重试后仍不健康，最近日志："
    journalctl -u keban-api --no-pager -n 30 >&2 || true
    die "api 没起来。上面的 Traceback 是根因，别跳过。"
fi
WEB_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 localhost:8501/ || true)"
[[ "$WEB_CODE" == 200 ]] && echo "    网页版 :8501 返回 200" \
    || warn "网页版 :8501 返回 ${WEB_CODE}（首次启动较慢，稍后 journalctl -u keban-web -f 看）"

# --------------------------------------------------------------------------- #
# 7. nginx
# --------------------------------------------------------------------------- #
log "7/8 配置 nginx"
cp "$APP_DIR/deploy/nginx-keban.conf" /etc/nginx/sites-available/keban
ln -sf /etc/nginx/sites-available/keban /etc/nginx/sites-enabled/keban
rm -f /etc/nginx/sites-enabled/default   # 不删会跟 keban 抢 80 端口
nginx -t
systemctl reload nginx
echo "    nginx 已加载（/ → 8501，/api/ → 8000，/h5/ → 静态文件）"

# --------------------------------------------------------------------------- #
# 8. 构建移动端 H5
# --------------------------------------------------------------------------- #
if [[ -z "$SERVER_IP" ]]; then
    SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -z "$SERVER_IP" ]] || is_private_ip "$SERVER_IP"; then
        PUBLIC_IP="$(detect_public_ip || true)"
        if [[ -n "$PUBLIC_IP" ]]; then
            echo "    网卡上是内网地址（${SERVER_IP}），改用探测到的公网地址 $PUBLIC_IP"
            SERVER_IP="$PUBLIC_IP"
        else
            die "探测不到公网 IP。请显式指定：SERVER_IP=你的公网IP ./deploy/bootstrap.sh"
        fi
    fi
fi
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://$SERVER_IP}"
echo "    对外地址：$PUBLIC_ORIGIN"

if [[ "$SKIP_H5" == 1 ]]; then
    log "8/8 跳过 H5 构建（SKIP_H5=1）"
    # 只有产物真的不存在时才喊 404 —— 重跑部署时旧产物还在，瞎报警会让人白忙
    if [[ -f "$APP_DIR/mobile/dist/build/h5/index.html" ]]; then
        echo "    沿用上次构建的产物（改了前端必须去掉 SKIP_H5 重新构建）"
    else
        warn "H5 从未构建过，/h5/ 现在是 404。补构建：cd $APP_DIR && PUBLIC_ORIGIN=$PUBLIC_ORIGIN ./deploy/update.sh"
    fi
else
    log "8/8 构建移动端 H5（API 指向 $PUBLIC_ORIGIN/api）"
    echo "    装 npm 依赖约 250MB，慢是正常的"
    sudo -u "$APP_USER" npm config set registry "$NPM_REGISTRY" >/dev/null
    (
        cd "$APP_DIR/mobile"
        sudo -u "$APP_USER" npm ci --silent
        sudo -u "$APP_USER" env VITE_API_BASE="$PUBLIC_ORIGIN/api" npm run build:h5
    )
    [[ -f "$APP_DIR/mobile/dist/build/h5/index.html" ]] \
        || die "H5 构建产物缺失，检查上面 npm 的输出"
    echo "    产物就绪：$APP_DIR/mobile/dist/build/h5/"
fi

# --------------------------------------------------------------------------- #
# 收尾
# --------------------------------------------------------------------------- #
# 大模型 key 配没配，直接影响要不要提示 —— 别对着已配好的环境反复催
NEED_LLM="$(python3 - "$SECRETS" <<'PY'
import sys, tomllib
try:
    d = tomllib.load(open(sys.argv[1], 'rb'))
    print(0 if (d.get('LLM_API_KEYS') or d.get('LLM_API_KEY')) else 1)
except Exception:
    print(1)
PY
)"

cat <<EOF

============================================================
 部署完成
============================================================
EOF

if [[ "$NEED_LLM" == 1 ]]; then
    cat <<EOF
 还需手工做一件事：填大模型 key（不填也能跑，但批改会退回本地规则引擎）
   nano $APP_DIR/.streamlit/secrets.toml    # 把 LLM_API_KEYS 那两行取消注释并填上
   systemctl restart keban-web keban-api

EOF
else
    echo " 大模型 key 已配置，无需额外操作。"
    echo
fi

cat <<EOF
 若公网打不开（四个入口全超时），是防火墙没放行 80：
   腾讯云轻量控制台 → 防火墙 → 添加 TCP:80

验收：
   网页版     $PUBLIC_ORIGIN/          登录 student / 123456
   API 文档   $PUBLIC_ORIGIN/api/docs
   API 健康   $PUBLIC_ORIGIN/api/health
   移动端 H5  $PUBLIC_ORIGIN/h5/        用手机浏览器打开

看日志：journalctl -u keban-web -f     journalctl -u keban-api -f
以后更新代码：cd $APP_DIR && PUBLIC_ORIGIN=$PUBLIC_ORIGIN ./deploy/update.sh

提醒：H5 的 API 地址是构建时写死的。换了域名或 IP，必须重跑 update.sh 重新构建，
      只重启服务不生效。
EOF
