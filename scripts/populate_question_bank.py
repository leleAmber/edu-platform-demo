"""并行全量生成题库：7 册教材 × 3 模块（预习/复习/模拟）× 各题型 → question_bank 表。

与 generate_questions.py 的分工：
- generate_questions.py 是「一次调用出一批题」的执行器（单条命令）；
- 本脚本是「调度器」，把 400+ 个「册×模块×单元×题型」任务放进线程池并发跑，
  否则按 44 秒/次串行要跑 6 小时以上，并发后约 1 小时。

用法（在仓库根目录运行）：
  .venv/bin/python scripts/populate_question_bank.py --dry-run          # 只看任务清单
  .venv/bin/python scripts/populate_question_bank.py --workers 5        # 全量并发生成
  .venv/bin/python scripts/populate_question_bank.py --books 必修一 --modules preview

设计：
- 幂等：底层靠 content_hash（含 book）去重，中断后可原样重跑，不会产生重复题；
- 每个任务是一个独立子进程，单任务失败不影响其他任务；失败的任务在汇总里列出；
- 并发数默认 5：LLM 层本身有「多 key 轮询 + 失败重试」，过高并发只会换来 429 限流。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core import textbook  # noqa: E402

# 用「当前解释器」跑子任务，避免 .venv / venv 路径写死导致依赖缺失
PYTHON = Path(sys.executable)
GENERATOR = REPO_ROOT / "scripts" / "generate_questions.py"

# 各模块出哪些题型 + 每类生成几篇/几道。
#
# 范围约束：三类题目都必须严格落在「用户选定的教材（+单元）」内，因此：
# - preview / review 页面目前只用 st.radio 渲染单选题（见 core/tutor_ai._db_quiz），
#   所以这里只出 choice；且每单元必须 ≥5 道有效单选题，
#   否则 _db_quiz 会回退到内置演示题（非选定教材），违反教材隔离。
#   故 count 取 10（>5）留出无效题被过滤后的余量。
# - mock 由 core/tutor_ai.assemble_mock_exam 按册组卷，任一题型不足都会整卷回退到
#   内置通用卷，所以 7 册都必须出齐下列 6 种题型。
MODULE_QTYPES: dict[str, dict[str, int]] = {
    "preview": {
        "choice": 10,
    },
    "review": {
        "choice": 10,
    },
    "mock": {
        "reading": 3,
        "seven_five": 2,
        "cloze": 2,
        "grammar_blank": 2,
        "writing_practical": 2,
        "writing_continuation": 2,
    },
}

_NEW_RE = re.compile(r"新增 (\d+) 题")


def build_jobs(books: list[str], modules: list[str]) -> list[dict]:
    """把「册 × 模块 × 单元 × 题型」展开成任务清单。"""
    jobs: list[dict] = []
    for book in books:
        units = textbook.get_units(book) or [None]
        for module in modules:
            # mock 是整卷模拟，不绑定单元；preview/review 逐单元出题。
            targets = [None] if module == "mock" else units
            for unit in targets:
                for qtype, count in MODULE_QTYPES[module].items():
                    jobs.append(
                        {"book": book, "module": module, "unit": unit, "qtype": qtype, "count": count}
                    )
    return jobs


def run_job(job: dict) -> tuple[dict, int, str]:
    """跑一个生成任务；返回 (任务, 本次新增题数, 输出尾部)。"""
    cmd = [
        str(PYTHON), str(GENERATOR),
        "--book", job["book"],
        "--module", job["module"],
        "--qtype", job["qtype"],
        "--count", str(job["count"]),
    ]
    if job["unit"]:
        cmd += ["--unit", job["unit"]]

    label = f"{job['book']}/{job['module']}/{job['unit'] or '通用'}/{job['qtype']}"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return job, 0, f"[超时] {label}"

    out = (proc.stdout or "") + (proc.stderr or "")
    match = _NEW_RE.search(out)
    new_count = int(match.group(1)) if match else 0
    if proc.returncode != 0 and new_count == 0:
        return job, 0, f"[失败 rc={proc.returncode}] {label}\n{out.strip()[-300:]}"
    return job, new_count, label


def main() -> int:
    parser = argparse.ArgumentParser(description="并行全量生成题库")
    parser.add_argument("--books", nargs="*", default=None, help="限定教材 key，缺省全部 7 册")
    parser.add_argument("--modules", nargs="*", default=None,
                        choices=["preview", "review", "mock"], help="限定模块，缺省全部 3 个")
    parser.add_argument("--workers", type=int, default=5, help="并发进程数（默认 5）")
    parser.add_argument("--dry-run", action="store_true", help="只打印任务清单，不执行")
    args = parser.parse_args()

    books = args.books or textbook.get_book_keys()
    unknown = [b for b in books if b not in textbook.get_book_keys()]
    if unknown:
        print(f"[错误] 未知教材 key：{unknown}，可选 {textbook.get_book_keys()}", file=sys.stderr)
        return 2
    modules = args.modules or list(MODULE_QTYPES)

    jobs = build_jobs(books, modules)
    print(f"任务总数：{len(jobs)}（{len(books)} 册 × {modules} × 题型），并发 {args.workers}")
    if args.dry_run:
        for job in jobs:
            print(f"  {job['book']}/{job['module']}/{job['unit'] or '通用'}/{job['qtype']} × {job['count']}")
        return 0

    started = time.time()
    total_new = 0
    failures: list[str] = []
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(run_job, job): job for job in jobs}
        for future in as_completed(futures):
            job, new_count, note = future.result()
            done += 1
            total_new += new_count
            elapsed = time.time() - started
            rate = done / elapsed * 60 if elapsed else 0
            eta = (len(jobs) - done) / rate if rate else 0
            print(f"[{done}/{len(jobs)}] +{new_count:>3} 题  {note}"
                  f"   （已用 {elapsed/60:.1f} 分，预计还需 {eta:.0f} 分）", flush=True)
            if note.startswith("["):
                failures.append(note)

    print(f"\n=== 汇总 ===")
    print(f"任务 {done}/{len(jobs)}，本次新增 {total_new} 题，耗时 {(time.time()-started)/60:.1f} 分钟。")
    if failures:
        print(f"\n以下 {len(failures)} 个任务失败/超时（可原样重跑，已成功的题目会被去重跳过）：")
        for item in failures:
            print(f"  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
