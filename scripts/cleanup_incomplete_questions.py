"""清理死题与不合规题：正文空数对不上、写作题语种搞反的行。

两类要清的数据：

1.「组不成卷」的死题。mock 的阅读/完形/七选五/语法填空是「一篇多空」，App 组卷时按
   passage 分组，且要求同一篇达到阈值才能成节（见 core/tutor_ai 的 section builder）：
   阅读 ≥4 题/篇、七选五 ≥5 空/篇（7 选项）、完形 ≥10 空/篇（4 选项）、语法填空 ≥10 空/篇。
   早期用能力不足的模型生成时，常产出「正文有 10 个 ___N___ 标记、blanks 只有 7~9 项」
   或缺标记的文章。这类行凑不满一篇，App 永远组不进去，属于死数据。

2. 写作题语种不合规的行。写作题的分工是「题目与要求中文，材料英文」：
   - 应用文：writing_prompt 必须是中文指令（模型常整段写成英文，如 "Write a notice for..."）；
   - 读后续写：passage 必须是英文故事且含 Paragraph 1/2 两段开头语，
     题目字段不得混入英文材料。
   判定与 scripts/generate_questions.py 的入库闸门保持一致。

用法（缺省只报告不删）：
  venv/bin/python scripts/cleanup_incomplete_questions.py            # 只报告，不删
  venv/bin/python scripts/cleanup_incomplete_questions.py --apply    # 执行删除

注意：务必在批量生成脚本**跑完之后**再执行。生成的每行是逐条 INSERT 的，
生成进行中扫描会把「正在写入的文章」误判为不完整并删掉。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_secrets_to_env() -> None:
    secrets_path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return
    data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        if data.get(name):
            os.environ.setdefault(name, str(data[name]))


_load_secrets_to_env()

from core import database  # noqa: E402
from sqlalchemy import bindparam, text  # noqa: E402

# 与 core/tutor_ai 的 section builder 一致：每篇至少要有多少个「有效空/题」才能成节
SECTION_MIN = {
    "reading": 4,
    "seven_five": 5,
    "cloze": 10,
    "grammar_blank": 10,
}


_CJK = re.compile(r"[一-鿿]")
_EN_WORD = re.compile(r"[A-Za-z]{2,}")

WRITING_QTYPES = ("writing_practical", "writing_continuation")


def _writing_dead_reason(row: dict) -> str | None:
    """写作行不合规的原因；合规返回 None。判定与生成脚本的入库闸门一致。"""
    prompt = row.get("writing_prompt") or ""
    passage = row.get("passage") or ""
    if not prompt:
        return "题目为空"
    if not _CJK.search(prompt):
        return "题目不是中文"
    if row["qtype"] == "writing_continuation":
        if not passage:
            return "没有材料"
        if _CJK.search(passage):
            return "材料含中文"
        if len(_EN_WORD.findall(passage)) < 30:
            return "材料英文过少"
        if "Paragraph 1" not in passage or "Paragraph 2" not in passage:
            return "材料缺少两段开头语"
        if "Paragraph" in prompt:
            return "段落开头语混进了题目字段"
    return None


def _valid(row: dict, qtype: str) -> bool:
    """该行是否算作「一个有效空/题」（按 App 各组卷函数的过滤条件）。"""
    if not row.get("answer"):
        return False
    options = row.get("options") or []
    if qtype in ("reading", "cloze"):
        return len(options) == 4
    if qtype == "seven_five":
        return len(options) == 7
    return True  # grammar_blank：只看 answer


def main() -> int:
    parser = argparse.ArgumentParser(description="清理组不成卷的 mock 死题与不合规写作题")
    parser.add_argument("--apply", action="store_true", help="真正执行删除（缺省只报告）")
    args = parser.parse_args()

    dead_ids: list[int] = []
    report: list[str] = []

    # 写作题语种不合规：题目应中文、材料应英文（全模块扫，含历史遗留行）
    write_dead = 0
    reasons: dict[str, int] = defaultdict(int)
    for qtype in WRITING_QTYPES:
        for row in database.get_questions(qtype=qtype, status=None, limit=5000):
            reason = _writing_dead_reason(row)
            if reason:
                dead_ids.append(row["id"])
                write_dead += 1
                reasons[f"{row['module']}/{qtype}：{reason}"] += 1
    for key in sorted(reasons):
        report.append(f"{key} —— {reasons[key]} 条")

    for qtype, minimum in SECTION_MIN.items():
        rows = database.get_questions(module="mock", qtype=qtype, status=None, limit=5000)
        # 按「教材 + 正文」分组：同一篇文章的行必须一起看
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            if not row.get("passage"):
                dead_ids.append(row["id"])  # 无正文的行本身就不完整
                continue
            groups[(row.get("book") or "", row["passage"])].append(row)

        for (book, _passage), group in groups.items():
            usable = [r for r in group if _valid(r, qtype)]
            if len(usable) < minimum:
                dead_ids.extend(r["id"] for r in group)
                report.append(
                    f"{book or '(无教材)'} / mock / {qtype}：一篇只有 {len(usable)} 个有效空/题"
                    f"（需 ≥{minimum}），整篇 {len(group)} 行判为死题"
                )

    print(f"扫描完成：发现 {len(dead_ids)} 行待清理（其中写作题语种不合规 {write_dead} 行）。")
    for line in report[:40]:
        print(f"  · {line}")
    if len(report) > 40:
        print(f"  …… 另有 {len(report) - 40} 项")

    if not dead_ids:
        print("无需清理。")
        return 0

    if not args.apply:
        print("\n[dry-run] 未删除。加 --apply 执行。")
        return 0

    # IN 里的列表要用 expanding 绑定，且一次不宜过多，分批 500 条
    statement = text("DELETE FROM question_bank WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    with database._raw_connect() as conn:
        deleted = 0
        for start in range(0, len(dead_ids), 500):
            chunk = tuple(dead_ids[start:start + 500])
            deleted += conn.execute(statement, {"ids": chunk}).rowcount
    print(f"\n已删除 {deleted} 行死题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
