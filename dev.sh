#!/usr/bin/env bash
# 本地同时启动三个模块，Ctrl-C 一次全退。
#
#   网页版 (Streamlit)  http://localhost:8501
#   API   (FastAPI)     http://127.0.0.1:8000/docs
#   移动端 (uni-app H5)  http://localhost:5173
#
# 三个进程共用仓库根目录的 .venv（api 没有独立虚拟环境）。
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "找不到 $PY，请先在仓库根目录建虚拟环境：" >&2
    echo "  python -m venv .venv && .venv/bin/pip install -r requirements.txt -r api/requirements.txt" >&2
    exit 1
fi

pids=()
cleanup() {
    echo
    echo "正在停止…"
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
}
trap cleanup INT TERM

echo "▶ API      http://127.0.0.1:8000"
(cd "$ROOT/api" && "$PY" run.py) &
pids+=($!)

echo "▶ 网页版   http://localhost:8501"
(cd "$ROOT" && "$PY" -m streamlit run app.py) &
pids+=($!)

echo "▶ 移动端   http://localhost:5173"
(cd "$ROOT/mobile" && npm run dev:h5) &
pids+=($!)

wait
