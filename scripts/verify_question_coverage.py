"""校验题库覆盖度：确认每册教材的预习/复习/模拟题都「够用」，不会回退到内置通用题。

背景（为什么需要这个校验）：
- 预习/复习页（core/tutor_ai._db_quiz）要求该单元在该模块下有 ≥5 道有效单选题，
  否则回退到内置演示题——那批题不属于用户选定的教材；
- 模拟卷（core/tutor_ai.assemble_mock_exam）要求该册各题型都够组卷，
  否则整卷回退到内置通用卷 MOCK_EXAM——同样会串教材。

本脚本按上面两处「真实取题条件」逐项检查，任何一项不达标都会列出，便于定点补题。

用法：
  .venv/bin/python scripts/verify_question_coverage.py            # 全量校验
  .venv/bin/python scripts/verify_question_coverage.py --book 必修一
退出码：0 全部达标；1 存在缺口。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_secrets_to_env() -> None:
    """把 .streamlit/secrets.toml 读入 os.environ，供 core.database 读取。"""
    secrets_path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return
    data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        if data.get(name):
            os.environ.setdefault(name, str(data[name]))


_load_secrets_to_env()

from core import database, textbook  # noqa: E402

# 预习/复习：页面用 st.radio 渲染 4 选项单选题，每单元每模块至少要有这么多题
MIN_QUIZ_CHOICE = 5
# 模拟卷各节的组卷阈值，与 core/tutor_ai 中的 section builder 保持一致
MOCK_READING_PASSAGES = 2      # 阅读理解需 2 篇，每篇 ≥4 题
MOCK_READING_PER_PASSAGE = 4
MOCK_SEVEN_FIVE_BLANKS = 5     # 七选五需一篇 ≥5 空（7 选项）
MOCK_CLOZE_BLANKS = 10         # 完形需一篇 ≥10 空（4 选项）
MOCK_GRAMMAR_BLANKS = 10       # 语法填空需 ≥10 空


def _valid_choice(row: dict) -> bool:
    return len(row.get("options") or []) == 4 and bool(row.get("answer"))


def _check_quiz(book: str, unit: str, module: str) -> str | None:
    """预习/复习：返回缺口说明；达标返回 None。"""
    rows = database.get_questions(book=book, module=module, unit=unit, qtype="choice", limit=200)
    usable = [r for r in rows if _valid_choice(r)]
    if len(usable) < MIN_QUIZ_CHOICE:
        return f"{book} / {module} / {unit}：有效单选题 {len(usable)} 道，需 ≥{MIN_QUIZ_CHOICE}"
    return None


def _passages_with(rows: list[dict], predicate, min_questions: int) -> int:
    """统计「满足条件的空/题数 ≥ min_questions」的文章篇数。"""
    by_passage: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("passage") and predicate(row):
            by_passage[row["passage"]] += 1
    return sum(1 for n in by_passage.values() if n >= min_questions)


def _check_mock(book: str) -> list[str]:
    """模拟卷：逐题型检查能否组卷，返回缺口说明列表。"""
    gaps: list[str] = []

    def fetch(qtype: str) -> list[dict]:
        return database.get_questions(book=book, module="mock", qtype=qtype, limit=300)

    readings = fetch("reading")
    if _passages_with(readings, _valid_choice, MOCK_READING_PER_PASSAGE) < MOCK_READING_PASSAGES:
        gaps.append(
            f"{book} / mock / reading：需 {MOCK_READING_PASSAGES} 篇各 ≥{MOCK_READING_PER_PASSAGE} 题，"
            f"实际 {_passages_with(readings, _valid_choice, MOCK_READING_PER_PASSAGE)} 篇"
        )

    seven = fetch("seven_five")
    if _passages_with(seven, lambda r: len(r.get("options") or []) == 7 and r.get("answer"),
                      MOCK_SEVEN_FIVE_BLANKS) < 1:
        gaps.append(f"{book} / mock / seven_five：需 1 篇 ≥{MOCK_SEVEN_FIVE_BLANKS} 空（7 选项）")

    cloze = fetch("cloze")
    if _passages_with(cloze, _valid_choice, MOCK_CLOZE_BLANKS) < 1:
        gaps.append(f"{book} / mock / cloze：需 1 篇 ≥{MOCK_CLOZE_BLANKS} 空")

    blanks = fetch("grammar_blank")
    if _passages_with(blanks, lambda r: bool(r.get("answer")), MOCK_GRAMMAR_BLANKS) < 1:
        gaps.append(f"{book} / mock / grammar_blank：需 1 篇 ≥{MOCK_GRAMMAR_BLANKS} 空")

    for qtype in ("writing_practical", "writing_continuation"):
        if not any(r.get("writing_prompt") for r in fetch(qtype)):
            gaps.append(f"{book} / mock / {qtype}：需 ≥1 道写作题")

    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description="校验题库覆盖度（按 App 真实取题条件）")
    parser.add_argument("--book", default=None, help="只校验某一册（key，如 必修一）")
    args = parser.parse_args()

    books = [args.book] if args.book else textbook.get_book_keys()
    unknown = [b for b in books if b not in textbook.get_book_keys()]
    if unknown:
        print(f"[错误] 未知教材 key：{unknown}", file=sys.stderr)
        return 2

    gaps: list[str] = []
    for book in books:
        units = textbook.get_units(book)
        for unit in units:
            for module in ("preview", "review"):
                gap = _check_quiz(book, unit, module)
                if gap:
                    gaps.append(gap)
        gaps.extend(_check_mock(book))
        print(f"[已检查] {book}（{len(units)} 单元 × 预习/复习 + 模拟卷）", flush=True)

    print("\n=== 校验结果 ===")
    if gaps:
        print(f"存在 {len(gaps)} 项缺口（下列位置会回退到非选定教材的内置题，需补题）：")
        for gap in gaps:
            print(f"  ✗ {gap}")
        return 1
    print("✓ 全部达标：各册预习/复习/模拟题均绑定选定教材，不会触发内置题回退。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
