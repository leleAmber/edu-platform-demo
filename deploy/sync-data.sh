#!/usr/bin/env bash
#
# 把本机开发库的数据同步到服务器
#
# ⚠️ 在**你的 Mac 上**跑。单向、全量、**会覆盖服务器上的同名表**。
#
# 用法：
#   ./deploy/sync-data.sh               # 先告诉你它会做什么，再让你确认
#   ./deploy/sync-data.sh --yes         # 跳过确认（脚本化调用）
#   ./deploy/sync-data.sh --dry-run     # 只在本机 dump 出来看看，不传输、不入库
#   ./deploy/sync-data.sh --replace-users  # 连用户也覆盖（会删掉服务器上独有的账号）
#
# 用户怎么处理（重要）：
#   默认**保留服务器上独有的账号**。线上随时可能有人注册，全量覆盖会把他们删掉，
#   而且不可逆。所以先备份服务器的 users 表，导入后把本机没有的账号补回去
#   （靠 username 唯一键去重，同名以本机为准）。
#   只有明确要「服务器上的用户也以本机为准」时才加 --replace-users。
#
# 为什么需要这个脚本：
#   服务器上的库是应用启动时自动建的，只有一个种子账号，**没有题库等内容数据**。
#   首次上线后不跑这个，生产环境就是个空库——登录进去什么都看不到。
#
# 两个设计取舍，别改：
#   1) 导入用服务器上的 root 执行。应用账号 keban_app 的授权里没有 DROP
#      （见 bootstrap.sh 的 GRANT），而全量 dump 带 DROP TABLE，用它导入会失败。
#      没有为了这个去放宽 keban_app 的权限——线上应用不该有删表能力。
#   2) 本机 secrets.toml 只用来取连接信息，**不传给服务器**。用户的密码哈希
#      是每行独立随机盐（core/database.py 的 hash_password），不依赖
#      AUTH_OTP_SECRET，所以迁过去照样能登录。
set -euo pipefail

TARGET="${KEBAN_TARGET:-keban}"
STAGE="${KEBAN_STAGE:-/tmp/edu-platform}"
LOCAL_SECRETS="${KEBAN_SECRETS:-.streamlit/secrets.toml}"
ASSUME_YES=0
DRY_RUN=0
REPLACE_USERS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y) ASSUME_YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --replace-users) REPLACE_USERS=1; shift ;;
        --target) TARGET="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f "$LOCAL_SECRETS" ]] || { echo "!! 找不到 $ROOT/$LOCAL_SECRETS" >&2; exit 1; }

# 本机连接信息走临时 defaults 文件，密码不落到命令行上（否则 ps 能看到）
CNF="$(mktemp -t keban-my)"
DUMP="$(mktemp -t keban-dump)"
trap 'rm -f "$CNF" "$DUMP" "$DUMP.gz"' EXIT

python3 - "$LOCAL_SECRETS" "$CNF" <<'PY'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], 'rb'))
with open(sys.argv[2], 'w') as f:
    f.write("[client]\nhost=%s\nport=%s\nuser=%s\npassword=%s\n" % (
        d.get('DB_HOST', '127.0.0.1'), d.get('DB_PORT', '3306'),
        d['DB_USER'], d['DB_PASSWORD']))
PY
chmod 600 "$CNF"

DB_NAME="$(python3 -c "import tomllib,sys;print(tomllib.load(open('$LOCAL_SECRETS','rb')).get('DB_NAME','keban_ai'))")"

echo "==> 1/6 从本机 dump 库 $DB_NAME"
mysqldump --defaults-extra-file="$CNF" \
    --single-transaction --quick --default-character-set=utf8mb4 \
    --set-gtid-purged=OFF --add-drop-table \
    --no-tablespaces \
    "$DB_NAME" > "$DUMP"
# --no-tablespaces：应用账号没有 PROCESS 权限，不加这个，MySQL 8 会在 dump
# 表空间时报 "Access denied; you need PROCESS privilege"（备份内容不受影响，
# 但会让脚本在 set -e 下失败）。而且我们也不需要表空间的元数据。

TABLES=$(grep -oE '^CREATE TABLE `[A-Za-z0-9_]+`' "$DUMP" | sed -E 's/^CREATE TABLE `(.*)`/\1/')
[[ -n "$TABLES" ]] || { echo "!! dump 里没有表，是不是 dump 空了？" >&2; exit 1; }

echo "    表：" $(echo "$TABLES" | tr '\n' ' ')
echo "    大小：$(du -h "$DUMP" | cut -f1)"
echo
echo "    本机各表行数："
for t in $TABLES; do
    n=$(mysql --defaults-extra-file="$CNF" -N -B -e "SELECT COUNT(*) FROM \`$DB_NAME\`.\`$t\`" 2>/dev/null || echo '?')
    printf "      %-18s %s\n" "$t" "$n"
done

if [[ "$DRY_RUN" == 1 ]]; then
    echo
    echo "--dry-run：止步于此，没有传输、没有入库。"
    echo "dump 内容保留在 ${DUMP}（退出后即删）"
    exit 0
fi

LOCAL_USERS="$(mysql --defaults-extra-file="$CNF" -N -B -e "SELECT username FROM \`$DB_NAME\`.\`users\`" 2>/dev/null || true)"

echo
if [[ "$REPLACE_USERS" == 1 ]]; then
    echo "!! --replace-users：服务器的 users 表会被本机完全覆盖，独有账号永久丢失。"
else
    echo "    服务器上独有的账号（本机没有，稍后会保留）："
    _found=0
    while IFS=$'\t' read -r _u _e; do
        [[ -z "$_u" ]] && continue
        if ! grep -qxF "$_u" <<<"$LOCAL_USERS"; then
            printf "      - %s  <%s>\n" "$_u" "$_e"
            _found=1
        fi
    done < <(ssh "$TARGET" "sudo mysql -N -B -e \"SELECT username, email FROM $DB_NAME.users\"" 2>/dev/null || true)
    (( _found )) || echo "      （无）"
fi

if [[ "$ASSUME_YES" != 1 ]]; then
    echo
    echo "!! 接下来会把上面这些表**先 DROP 再重建**到服务器 $TARGET 的 $DB_NAME 库。"
    echo "!! 这些表在服务器上的现有数据会全部丢失。"
    read -r -p "确认继续？输入 yes：" ans
    [[ "$ans" == "yes" ]] || { echo "已取消。"; exit 1; }
fi

echo
echo "==> 2/6 压缩并传到服务器"
gzip -9 -c "$DUMP" > "$DUMP.gz"
scp -q "$DUMP.gz" "$TARGET:/tmp/keban_data.sql.gz"
echo "    已传到 /tmp/keban_data.sql.gz（$(du -h "$DUMP.gz" | cut -f1)）"

if [[ "$REPLACE_USERS" == 1 ]]; then
    echo
    echo "==> 3/6 跳过用户备份（--replace-users）"
else
    echo
    echo "==> 3/6 备份服务器上的 users 表"
    ssh "$TARGET" "sudo mysql -N -B $DB_NAME -e \"
        DROP TABLE IF EXISTS _users_prod_backup;
        CREATE TABLE _users_prod_backup AS SELECT * FROM users;
        SELECT CONCAT('    已备份 ', COUNT(*), ' 个账号') FROM _users_prod_backup;\""
fi

echo
echo "==> 4/6 用 root 导入（keban_app 没有 DROP 权限，必须用 root）"
ssh "$TARGET" "gunzip -c /tmp/keban_data.sql.gz | sudo mysql $DB_NAME && rm -f /tmp/keban_data.sql.gz"
echo "    导入完成"

echo
echo "==> 5/6 回填服务器独有账号并重启服务"
if [[ "$REPLACE_USERS" == 1 ]]; then
    echo "    （已跳过回填）"
else
    # 不带 id 插入，让自增重新分配：本机与服务器的 id 是各自独立生成的，
    # 直接带着 id 插会撞主键，INSERT IGNORE 会把账号静默丢掉。
    ssh "$TARGET" "sudo mysql $DB_NAME -e \"
        INSERT IGNORE INTO users (username, email, password, role, vip_until, vip_plan, openid, created_at)
        SELECT b.username, b.email, b.password, b.role, b.vip_until, b.vip_plan, b.openid, b.created_at
          FROM _users_prod_backup b
         WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.username = b.username);
        SELECT CONCAT('    回填 ', ROW_COUNT(), ' 个账号') AS '';
        DROP TABLE _users_prod_backup;\""
fi
ssh "$TARGET" "sudo systemctl restart keban-web keban-api && sleep 5 && systemctl is-active keban-web keban-api | tr '\n' ' ' && echo"

echo
echo "==> 6/6 校验：本机 vs 服务器 行数对比"
MISMATCH=0
for t in $TABLES; do
    local_n=$(mysql --defaults-extra-file="$CNF" -N -B -e "SELECT COUNT(*) FROM \`$DB_NAME\`.\`$t\`" 2>/dev/null || echo '?')
    remote_n=$(ssh "$TARGET" "sudo mysql -N -B -e 'SELECT COUNT(*) FROM \`$DB_NAME\`.\`$t\`'" 2>/dev/null || echo '?')
    if [[ "$local_n" == "$remote_n" ]]; then
        printf "    %-18s %6s  ✓\n" "$t" "$local_n"
    elif [[ "$t" == "users" && "$REPLACE_USERS" != 1 ]]; then
        # 默认模式会保留服务器上独有的账号，所以 users 比本机多**正是预期结果**
        printf "    %-18s 本机 %s / 服务器 %s  ✓（多出的是服务器独有账号）\n" "$t" "$local_n" "$remote_n"
    else
        printf "    %-18s 本机 %s / 服务器 %s  ✗\n" "$t" "$local_n" "$remote_n"
        MISMATCH=1
    fi
done

echo
echo "    服务器上现有账号："
ssh "$TARGET" "sudo mysql -N -B -e 'SELECT username, role FROM $DB_NAME.users ORDER BY id'" | sed 's/^/      /'

echo
if [[ "$MISMATCH" == 1 ]]; then
    echo "!! 有表行数对不上，别忽略——上面标 ✗ 的就是。" >&2
    exit 1
fi
echo "数据同步完成。"
