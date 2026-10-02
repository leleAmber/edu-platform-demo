#!/usr/bin/env bash
# 每日自动增量生成题库（配合服务器 crontab 使用）。
# 幂等：同命令重复执行靠 content_hash（含 book）去重，不会产生重复题。
# crontab 示例（每天 03:00）：
#   0 3 * * * cd /path/to/edu-platform-demo && scripts/scheduled_generate.sh
set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/scripts/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/generate_$(date +%Y%m%d_%H%M%S).log"

{
  echo "=== 开始 $(date '+%F %T') ==="
  for BOOK in 必修一 必修二 必修三 选一 选二 选三 选四; do
    # 预习/复习：按单元出单选题（课本配套练习）
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module preview --qtype choice --count 5
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module review  --qtype choice --count 5
    # 模拟卷：完整新高考题型
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype reading --count 2
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype seven_five --count 1
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype cloze --count 1
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype grammar_blank --count 1
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype writing_practical --count 1
    "$PY" "$REPO_ROOT/scripts/generate_questions.py" --book "$BOOK" --module mock --qtype writing_continuation --count 1
  done
  echo "=== 结束 $(date '+%F %T') ==="
} >> "$LOG" 2>&1
