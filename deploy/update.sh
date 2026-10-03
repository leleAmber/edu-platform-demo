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

# 对外访问地址：默认取本机第一个 IP。有域名后改成 PUBLIC_ORIGIN=https://your-domain.com
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://$(hostname -I 2>/dev/null | awk '{print $1}')}"

echo "==> 1/5 拉取最新代码"
git pull --ff-only

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
