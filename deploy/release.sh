#!/usr/bin/env bash
#
# 本机发版：把代码推到服务器并重启
#
# ⚠️ 这个脚本在**你的 Mac 上**跑，不是在服务器上跑。
#    服务器上要跑的是 bootstrap.sh / update.sh。
#
# 用法：
#   ./deploy/release.sh                     # 全量：推代码 → 装依赖 → 重建 H5 → 重启
#   ./deploy/release.sh --fast              # 只改了 Python 后端：跳过 apt 与 H5 构建
#   ./deploy/release.sh --target root@1.2.3.4 --origin http://example.com
#
# 可用环境变量覆盖默认值：KEBAN_TARGET / KEBAN_ORIGIN / KEBAN_STAGE
#
# 为什么发版不用 git：这台服务器拉 GitHub 完全不通（实测 20 秒零字节，
# 见 deploy/README.md），所以代码是用 rsync 推的，**服务器上没有 .git**。
#
# 什么时候必须全量（不能用 --fast）：
#   - 改了 mobile/ 下任何前端代码 —— H5 的 API 地址是构建时写死的
#   - 换了域名或 IP —— 同上，必须重新构建
#   - 加了系统级依赖（apt 包）
set -euo pipefail

TARGET="${KEBAN_TARGET:-keban}"                        # ~/.ssh/config 里的别名，或 user@host
PUBLIC_ORIGIN="${KEBAN_ORIGIN:-http://111.231.10.101}"
STAGE="${KEBAN_STAGE:-/tmp/edu-platform}"
FAST=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast)   FAST=1; shift ;;
        --target) TARGET="$2"; shift 2 ;;
        --origin) PUBLIC_ORIGIN="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f app.py && -d core ]] || { echo "!! 这里不像仓库根目录：$ROOT" >&2; exit 1; }

# 对外地址可能是带协议的，bootstrap.sh 需要一个纯主机名
HOST="${PUBLIC_ORIGIN#http://}"; HOST="${HOST#https://}"; HOST="${HOST%%/*}"

echo "==> 1/3 推代码到 $TARGET:$STAGE"
echo "    目标对外地址：$PUBLIC_ORIGIN"
ssh "$TARGET" "rm -rf $STAGE && mkdir -p $STAGE"
rsync -az --stats \
    --exclude '.git' --exclude 'venv' --exclude '.venv' --exclude 'node_modules' \
    --exclude '__pycache__' --exclude 'mobile/dist' --exclude '.DS_Store' \
    --exclude '.streamlit/secrets.toml' \
    ./ "$TARGET:$STAGE/" \
    | grep -E 'Number of files transferred|Total transferred file size' | sed 's/^/    /'
# 注意：这里**排除** .streamlit/secrets.toml —— 服务器上那份是它自己生成的，
# 数据库密码和 AUTH_OTP_SECRET 跟本机不同，覆盖过去会让应用连不上库。

echo
echo "==> 2/3 在服务器上执行部署（幂等：不动数据库，不覆盖 secrets.toml）"
[[ "$FAST" == 1 ]] && echo "    --fast：跳过 apt 与 H5 构建"
ssh "$TARGET" "sudo env SKIP_APT=$FAST SKIP_H5=$FAST SERVER_IP='$HOST' PUBLIC_ORIGIN='$PUBLIC_ORIGIN' bash -c 'cd $STAGE && bash deploy/bootstrap.sh'"

echo
echo "==> 3/3 从本机验收（走公网，能真实反映防火墙与 nginx 状态）"
FAIL=0
for p in "/" "/api/health" "/api/docs" "/h5/"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$PUBLIC_ORIGIN$p" || echo 000)
    printf "    %-13s HTTP %s\n" "$p" "$code"
    [[ "$code" == 200 ]] || FAIL=1
done

if [[ "$FAIL" == 1 ]]; then
    echo
    echo "!! 有入口不是 200。排查顺序：" >&2
    echo "   1) ssh $TARGET 'systemctl status keban-web keban-api'" >&2
    echo "   2) ssh $TARGET 'journalctl -u keban-api -n 50 --no-pager'" >&2
    echo "   3) 除非 4 个全 404，否则多半不是防火墙问题" >&2
    exit 1
fi
echo
echo "发版完成：$PUBLIC_ORIGIN"
