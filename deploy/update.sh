#!/usr/bin/env bash
# 服务器上的更新脚本：拉代码 → 装依赖 → 构建 H5 → 重启服务
#
# 用法：
#   cd /srv/edu-platform && ./deploy/update.sh
#   PUBLIC_ORIGIN=http://1.2.3.4 ./deploy/update.sh      # 显式指定对外地址
#
# 说明：H5 的 API 地址是**构建时写死**的（VITE_API_BASE），所以换域名/IP 后
#       必须重跑本脚本重新构建，光重启 nginx 不生效。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 对外访问地址：显式传 PUBLIC_ORIGIN=http://你的域名 最稳。
# 不传则自动探测——注意云服务器（腾讯云轻量等）网卡上只有内网 IP，公网是 NAT 的，
# 直接把 hostname -I 的结果写进 H5 会让手机端白屏，所以内网地址会被替换成公网探测结果。
is_private_ip() {
    [[ "$1" =~ ^(10\.|127\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.) ]]
}

if [[ -z "${PUBLIC_ORIGIN:-}" ]]; then
    _ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -z "$_ip" ]] || is_private_ip "$_ip"; then
        for _url in https://api.ipify.org https://ifconfig.me/ip https://ipinfo.io/ip; do
            _ip="$(curl -fsS --max-time 5 "$_url" 2>/dev/null | tr -d '[:space:]')" || continue
            [[ "$_ip" =~ ^[0-9]+(\.[0-9]+){3}$ ]] && break
            _ip=""
        done
        [ -n "$_ip" ] || { echo "!! 探测不到公网 IP，请显式指定 PUBLIC_ORIGIN=http://你的地址" >&2; exit 1; }
    fi
    PUBLIC_ORIGIN="http://$_ip"
    echo "==> 对外地址自动探测为 ${PUBLIC_ORIGIN}（要改就显式传 PUBLIC_ORIGIN=...）"
fi

echo "==> 1/5 更新代码"
if [[ -d "$ROOT/.git" ]]; then
    git pull --ff-only
else
    # 大陆机器常因拉不动 GitHub 而改用 rsync 传代码，那样服务器上没有 .git。
    # 此时不能直接 git pull（在非 git 目录里会因 set -e 让整个脚本退出）。
    echo "    服务器上无 .git —— 代码是用 rsync 传的，跳过 git pull"
    echo "    更新方式：在本机重跑 rsync 推送，或改用 git 克隆的部署方式"
fi

echo "==> 2/5 安装 Python 依赖"
"$ROOT/.venv/bin/pip" install -q -r requirements.txt -r api/requirements.txt

echo "==> 3/5 构建移动端 H5（API 指向 ${PUBLIC_ORIGIN}/api）"
cd "$ROOT/mobile"
npm ci --silent
VITE_API_BASE="${PUBLIC_ORIGIN}/api" npm run build:h5

echo "==> 4/5 检查 secrets.toml"
if [ ! -f "$ROOT/.streamlit/secrets.toml" ]; then
    echo "!! 缺少 $ROOT/.streamlit/secrets.toml" >&2
    echo "!! 该文件被 .gitignore 忽略，不会随 git 下来，必须在服务器上手动创建。" >&2
    echo "!! 参考仓库 README 的「第 2 步：填写连接信息」。" >&2
    exit 1
fi

echo "==> 5/5 重启服务"
sudo systemctl restart keban-web keban-api
sleep 2
sudo systemctl --no-pager --lines=0 status keban-web keban-api || true

echo
echo "完成。H5: ${PUBLIC_ORIGIN}/h5/   网页版: ${PUBLIC_ORIGIN}/   API 文档: ${PUBLIC_ORIGIN}/api/docs"
