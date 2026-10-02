"""离线批量生成原创题库：调用大模型生成题，去重后写入 question_bank 表（按教材隔离）。

用法（在仓库根目录运行，用项目虚拟环境的 Python）：
  .venv/bin/python scripts/generate_questions.py --book 必修一 --module preview --unit "Unit1 Teenage Life" --qtype choice --count 5
  .venv/bin/python scripts/generate_questions.py --book 必修一 --module mock --qtype reading --count 3 --dry-run
  .venv/bin/python scripts/generate_questions.py --all --module preview --count 5        # 全部 7 册

设计：
- 喂给模型的是「教材单元知识点（单词 + 重点句型）+ 高考题型结构 + 评分细则」，产出原创题；
- 同一命令可重复执行：内容 hash（含 book）去重，幂等，便于 cron 每日增量跑；
- 题型分两类：single（一题一行）与 article（一篇多空，入库时按空拆成多行、passage 重复存储）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_secrets_to_env() -> None:
    """把 .streamlit/secrets.toml 读入 os.environ，供 core.database / core.llm 读取。"""
    secrets_path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        print("[警告] 未找到 .streamlit/secrets.toml，依赖环境变量或跳过。", file=sys.stderr)
        return
    data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    for name in (
        "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
        "LLM_BASE_URL", "LLM_MODEL", "LLM_VISION_MODEL",
    ):
        value = data.get(name)
        if value:
            os.environ.setdefault(name, str(value))
    api_keys = data.get("LLM_API_KEYS")
    if api_keys and not os.environ.get("LLM_API_KEYS"):
        os.environ["LLM_API_KEYS"] = json.dumps([str(k) for k in api_keys], ensure_ascii=False)
    elif data.get("LLM_API_KEY") and not os.environ.get("LLM_API_KEY"):
        os.environ["LLM_API_KEY"] = str(data["LLM_API_KEY"])


_load_secrets_to_env()

from core import database, llm, textbook, tutor_ai  # noqa: E402

_SYSTEM = (
    "你是一位资深高中英语命题老师，熟悉人教版教材与高考英语题型、评分细则。"
    "请根据给定的知识点/题型要求原创生成高中英语练习题，不得复制任何教材或真题原文。"
    "严格只输出一个 JSON 对象，不要输出任何解释、注释或代码块标记，格式为："
    '{"questions": [ ... ]}'
)

_QTYPES = (
    "choice", "reading", "seven_five", "cloze", "grammar_blank",
    "writing_practical", "writing_continuation",
)

# kind=single：一题一行；kind=article：一篇多空（blanks 数组，入库时拆成多行）
_QTYPE_SPEC = {
    "choice": {
        "kind": "single", "label": "单项选择",
        "rules": (
            "4 个选项，仅 1 个正确，干扰项有迷惑性；题干语境完整、考点明确，考查给定知识点；"
            "选项文本不要带 A./B./C./D. 前缀；answer 填正确选项完整原文，与 options 中某一项逐字符一致。"
        ),
        "fields": '{"question": "题干", "options": ["选项1", "选项2", "选项3", "选项4"], "answer": "正确选项完整原文", "explain": "中文解析"}',
    },
    "reading": {
        "kind": "article", "label": "阅读理解",
        "rules": (
            "原创一篇 120~200 词英文短文（不得用教材或真题原文），后接 4 道单选题（每题 4 个选项，仅 1 个正确）；"
            "答案能在文中找到依据；选项不要带 A./B./C./D. 前缀；answer 填正确选项完整原文。"
        ),
        "fields": '{"passage": "原创英文短文", "questions": [{"question": "题干", "options": ["选项1", "选项2", "选项3", "选项4"], "answer": "正确选项完整原文", "explain": "中文解析"} ... 共 4 项]}',
    },
    "seven_five": {
        "kind": "article", "label": "七选五",
        "rules": (
            "原创一篇短文，中间挖 5 个空（用 ___1___ 到 ___5___ 表示），给出 7 个备选句子；"
            "其中 5 个填入 5 空，2 个为干扰项；答案能从上下文逻辑推出。"
        ),
        "fields": '{"passage": "含 5 个空的原创短文", "options": ["选项1"..."选项7" 共 7 项], "blanks": [{"question": "该空所在句/上下文", "answer": "正确选项完整原文", "explain": "解析"} ... 共 5 项]}',
    },
    "cloze": {
        "kind": "article", "label": "完形填空",
        "rules": (
            "原创一篇短文，挖 10 个空（用 ___1___ 到 ___10___ 表示），每空 4 个选项（词或短语），"
            "仅 1 个正确，考查词汇辨析与语境理解。"
        ),
        "fields": '{"passage": "含 10 个空的原创短文", "blanks": [{"question": "该空所在句", "options": ["选项1", "选项2", "选项3", "选项4"], "answer": "正确词", "explain": "解析"} ... 共 10 项]}',
    },
    "grammar_blank": {
        "kind": "article", "label": "语法填空",
        "rules": (
            "原创一篇短文，挖 10 个空（用 ___1___ 到 ___10___ 表示），考查语法/词形变化；"
            "括号内给提示词或纯语境，答案唯一。"
        ),
        "fields": '{"passage": "含 10 个空的原创短文", "blanks": [{"question": "该空所在句(含提示)", "answer": "正确填词", "explain": "解析"} ... 共 10 项]}',
    },
    "writing_practical": {
        "kind": "single", "label": "应用文写作",
        "rules": (
            "出一篇高中应用文（书信/通知/发言稿/建议信等），给出题目与要求（词数、要点、格式）。"
        ),
        "fields": '{"writing_prompt": "写作题目", "writing_requirements": ["要求1", "要求2"], "answer": "参考范文要点", "explain": "评分要点"}',
    },
    "writing_continuation": {
        "kind": "single", "label": "读后续写",
        "rules": (
            "给出一段原创故事开头（含时间地点人物情节），要求续写，给出词数与内容要求。"
        ),
        "fields": '{"passage": "故事开头(原创)", "writing_prompt": "续写要求", "writing_requirements": ["要求1", "要求2"], "answer": "参考续写要点", "explain": "评分要点"}',
    },
}


# --------------------------------------------------------------------------- #
# 养料（知识点材料）
# --------------------------------------------------------------------------- #
def _unit_material(book: str, unit: str) -> str:
    """从教材内容提取某单元的知识点养料（核心词汇 + 重点句型）。"""
    content = tutor_ai.get_unit_content(book, unit)
    lines = [f"教材：{book}", f"单元：{unit}", f"主题：{content.get('theme', '')}"]

    words = content.get("words") or []
    if words:
        lines.append("核心词汇：")
        for word in words[:30]:
            lines.append(f"- {word.get('word', '')}（{word.get('pos', '')}）{word.get('explain', '')}")

    patterns = content.get("sentence_patterns") or []
    if patterns:
        lines.append("重点句型：")
        for p in patterns[:15]:
            lines.append(f"- {p.get('pattern', '')}（{p.get('explain', '')}）")

    return "\n".join(lines)


def _material_text(path: str | None, book: str, unit: str | None) -> str:
    """取养料文本：优先外部文件；否则单元知识点；mock 无单元时为空（自主选题）。"""
    if path:
        return Path(path).read_text(encoding="utf-8")
    if unit:
        return _unit_material(book, unit)
    return ""


def _build_prompt(module: str, qtype: str, material: str, count: int, book: str) -> str:
    """组装一次生成请求的用户提示。"""
    spec = _QTYPE_SPEC[qtype]
    module_hint = {
        "preview": "课前预习：难度偏低，聚焦本单元新学知识点，帮助预读",
        "review": "课后复习：难度中等，覆盖本单元核心词汇、语法与语篇",
        "mock": "高考模拟：严格贴近高考题型、难度与设问方式，不限于单一单元",
    }.get(module, "")

    if spec["kind"] == "article":
        lines = [
            f"请原创生成 {count} 篇「{spec['label']}」文章（每篇含要求的空数与选项）。",
        ]
    else:
        lines = [
            f"请原创生成 {count} 道「{spec['label']}」题。",
        ]
    lines += [
        f"【适用场景】{module_hint}",
        f"【题型】{spec['label']}",
        f"【命题要求】{spec['rules']}",
    ]
    if material and material.strip():
        lines.append("【可参考的知识点/话题材料】")
        lines.append(material.strip())
    else:
        lines.append("【话题】自主选择一个贴近高中校园生活或社会热点的原创话题。")
    lines.append("严格只输出一个 JSON 对象，字段名保持一致：")
    lines.append('{"questions": [ ' + spec["fields"] + ", ... ]}")
    lines.append("解析用中文。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 规范化 + 去重
# --------------------------------------------------------------------------- #
def _content_hash(book: str, grade: str, qtype: str, passage: str, question: str,
                  options: list, answer: str, writing_prompt: str) -> str:
    """题目归一化文本的 SHA-1（含教材维度），用于唯一键去重。"""
    canonical = json.dumps(
        [book, grade, qtype, passage or "", question or "", options or [], answer or "", writing_prompt or ""],
        ensure_ascii=False,
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


_OPTION_PREFIX = re.compile(r"^[A-Ga-g]\s*[.、:：)）]\s*")


def _strip_option_prefix(text: str) -> str:
    return _OPTION_PREFIX.sub("", text, count=1).strip()


def _clean_options(options) -> list[str]:
    if not isinstance(options, list):
        return []
    return [_strip_option_prefix(str(o).strip()) for o in options if str(o).strip()]


def _map_answer(answer: str, options: list[str]) -> str:
    """模型偶尔只回字母（"B"），映射回对应选项全文。"""
    a = _strip_option_prefix(answer)
    if len(a) == 1 and a.upper() in "ABCDEFG" and options:
        index = ord(a.upper()) - ord("A")
        if 0 <= index < len(options):
            return options[index]
    return a


def _single_row(raw: dict, book: str, grade: str, module: str, unit: str | None, qtype: str) -> dict | None:
    """single 类题型：把模型输出的一道题规范化成一行。"""
    question = str(raw.get("question") or "").strip()
    passage = str(raw.get("passage") or "").strip()
    writing_prompt = str(raw.get("writing_prompt") or "").strip()
    explain = str(raw.get("explain") or "").strip()
    options = _clean_options(raw.get("options"))
    answer = _map_answer(str(raw.get("answer") or "").strip(), options) if options else str(raw.get("answer") or "").strip()

    requirements = raw.get("writing_requirements")
    requirements = [str(r).strip() for r in requirements if str(r).strip()] if isinstance(requirements, list) else []

    if qtype in ("writing_practical", "writing_continuation"):
        if not writing_prompt:
            return None
        question = ""
    else:
        if not question:
            return None
        if qtype == "choice" and (len(options) != 4 or not answer or answer not in options):
            return None

    content_hash = _content_hash(book, grade, qtype, passage, question, options, answer, writing_prompt)
    return {
        "content_hash": content_hash, "book": book, "grade": grade, "module": module,
        "unit": unit or None, "qtype": qtype, "passage": passage or None, "question": question,
        "options": options, "answer": answer or None, "explain": explain or None,
        "writing_prompt": writing_prompt or None, "writing_requirements": requirements,
        "score": 1, "difficulty": 2, "status": 1, "source": "llm",
    }


def _article_rows(raw: dict, book: str, grade: str, module: str, unit: str | None, qtype: str) -> list[dict]:
    """article 类题型：把一篇多空的文章拆成多行（passage 重复存储）。"""
    passage = str(raw.get("passage") or "").strip()
    blanks = raw.get("blanks")
    if not passage or not isinstance(blanks, list) or not blanks:
        return []

    shared_options = _clean_options(raw.get("options"))  # 七选五的 7 个选项
    rows = []
    for blank in blanks:
        if not isinstance(blank, dict):
            continue
        question = str(blank.get("question") or "").strip()
        explain = str(blank.get("explain") or "").strip()
        if qtype == "seven_five":
            options = shared_options
            answer = _map_answer(str(blank.get("answer") or "").strip(), options)
            if len(options) != 7 or not answer or answer not in options:
                continue
        elif qtype == "cloze":
            options = _clean_options(blank.get("options"))
            answer = _map_answer(str(blank.get("answer") or "").strip(), options)
            if len(options) != 4 or not answer or answer not in options:
                continue
        else:  # grammar_blank
            options = []
            answer = str(blank.get("answer") or "").strip()
            if not answer:
                continue

        if not question:
            continue
        content_hash = _content_hash(book, grade, qtype, passage, question, options, answer, "")
        rows.append({
            "content_hash": content_hash, "book": book, "grade": grade, "module": module,
            "unit": unit or None, "qtype": qtype, "passage": passage, "question": question,
            "options": options, "answer": answer, "explain": explain or None,
            "writing_prompt": None, "writing_requirements": [],
            "score": 1, "difficulty": 2, "status": 1, "source": "llm",
        })
    return rows


def _reading_rows(raw: dict, book: str, grade: str, module: str, unit: str | None) -> list[dict]:
    """阅读理解：一篇多题，每题拆成一行（passage 重复存储）。"""
    passage = str(raw.get("passage") or "").strip()
    questions = raw.get("questions")
    if not passage or not isinstance(questions, list) or not questions:
        return []
    rows = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        question = str(q.get("question") or "").strip()
        explain = str(q.get("explain") or "").strip()
        options = _clean_options(q.get("options"))
        answer = _map_answer(str(q.get("answer") or "").strip(), options)
        if not question or len(options) != 4 or not answer or answer not in options:
            continue
        content_hash = _content_hash(book, grade, "reading", passage, question, options, answer, "")
        rows.append({
            "content_hash": content_hash, "book": book, "grade": grade, "module": module,
            "unit": unit or None, "qtype": "reading", "passage": passage, "question": question,
            "options": options, "answer": answer, "explain": explain or None,
            "writing_prompt": None, "writing_requirements": [],
            "score": 1, "difficulty": 2, "status": 1, "source": "llm",
        })
    return rows


def _normalize(raw: dict, book: str, grade: str, module: str, unit: str | None, qtype: str) -> list[dict]:
    """把模型输出的一道题/一篇文章规范化成一行或多行。"""
    if qtype == "reading":
        return _reading_rows(raw, book, grade, module, unit)
    if _QTYPE_SPEC[qtype]["kind"] == "article":
        return _article_rows(raw, book, grade, module, unit, qtype)
    row = _single_row(raw, book, grade, module, unit, qtype)
    return [row] if row else []


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def _books(args) -> list[dict]:
    if args.all:
        return textbook.get_books()
    if not args.book:
        print("[错误] 请指定 --book 或 --all。", file=sys.stderr)
        return []
    for b in textbook.get_books():
        if b.get("key") == args.book:
            return [b]
    print(f"[错误] 未知教材 key：{args.book}，可选 {textbook.get_book_keys()}", file=sys.stderr)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="离线批量生成原创题库并写入 question_bank 表")
    parser.add_argument("--book", default=None, help="教材 key（如 必修一）；不填用 --all")
    parser.add_argument("--all", action="store_true", help="遍历全部教材")
    parser.add_argument("--module", required=True, choices=["preview", "review", "mock"], help="目标模块")
    parser.add_argument("--unit", default=None, help="单元名（preview/review 用；缺省遍历该书全部单元）")
    parser.add_argument("--qtype", default="all", help="题型：choice/reading/seven_five/cloze/grammar_blank/writing_practical/writing_continuation/all")
    parser.add_argument("--count", type=int, default=5, help="每个「单元×题型」生成数量（article 类为文章篇数）")
    parser.add_argument("--material", default=None, help="养料文本文件路径（可选，覆盖内置单元知识点）")
    parser.add_argument("--dry-run", action="store_true", help="只生成并打印，不写库")
    args = parser.parse_args()

    books = _books(args)
    if not books:
        return 2

    if args.qtype == "all":
        qtypes = list(_QTYPES)
    elif args.qtype in _QTYPES:
        qtypes = [args.qtype]
    else:
        print(f"[错误] 未知题型：{args.qtype}，可选 {_QTYPES}", file=sys.stderr)
        return 2

    total_new = total_dup = total_invalid = 0

    for book in books:
        book_key = book.get("key", "")
        grade = book.get("grade", "高一")
        if args.module in ("preview", "review"):
            units = [args.unit] if args.unit else [u.get("unit", "") for u in book.get("units", [])]
        else:
            units = [args.unit]  # mock 一般不带单元

        for unit in units:
            unit_label = unit or "通用"
            material = _material_text(args.material, book_key, unit) if args.module in ("preview", "review") else ""
            for qtype in qtypes:
                print(f"\n=== {book_key} / {args.module} / {unit_label} / {qtype} · 生成 {args.count} ===")
                prompt = _build_prompt(args.module, qtype, material, args.count, book_key)
                # 大模型偶尔返回空/失败，重试几次提升每日 cron 的稳定性
                raw_list = None
                for _attempt in range(3):
                    raw_list = llm.generate_questions(_SYSTEM, prompt)
                    if raw_list:
                        break
                if not raw_list:
                    print("[警告] 模型未返回结果（未配置 key 或调用失败），已跳过。")
                    continue

                for raw in raw_list:
                    rows = _normalize(raw, book_key, grade, args.module, unit, qtype)
                    if not rows:
                        total_invalid += 1
                        print("  - [无效] 字段不完整，跳过")
                        continue
                    for q in rows:
                        preview = (q["question"] or q["writing_prompt"])[:36]
                        if args.dry_run:
                            print(f"  + [dry-run] {qtype}: {preview}")
                            continue
                        if database.has_question(q["content_hash"]):
                            total_dup += 1
                            print(f"  - [重复] {qtype}: {preview}")
                            continue
                        new_id = database.add_question(q)
                        if new_id is None:
                            total_dup += 1
                            print(f"  - [重复] {qtype}: {preview}")
                        else:
                            total_new += 1
                            print(f"  + [新增 #{new_id}] {qtype}: {preview}")

    print("\n=== 汇总 ===")
    print(f"新增 {total_new} 题，重复跳过 {total_dup} 题，无效跳过 {total_invalid} 题。")
    if not args.dry_run and total_new == 0:
        print("[提示] 本次无新增（可能全部重复）。可换知识点/题型/参数后重试。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
