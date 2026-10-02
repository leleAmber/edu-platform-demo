"""离线提取 7 册人教高中英语教材：单词表 + 重点句型(Notes) → data/textbooks/*.json

用法（在仓库根目录运行，用项目虚拟环境的 Python）：
  .venv/bin/python scripts/extract_textbooks.py --book 必修一
  .venv/bin/python scripts/extract_textbooks.py --all
  .venv/bin/python scripts/extract_textbooks.py --book 必修一 --no-llm   # 只看分段，不调大模型

设计：
- 教材 PDF 为数字版，pymupdf 可直接取文本；
- 单词表在附录 "Words and Expressions in Each Unit"，按 "Welcome Unit / Unit N" 分段；
- 重点句型在 "Notes" 附录，同样按 "Unit N" 分段；
- 分段后的原始文本交给大模型（llm.structure）整理成结构化 JSON，避免手写脆弱正则；
- 单元标题/中文主题为脚本内常量（与教材目录一一对应），不靠解析。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 教材根目录
PDF_DIR = REPO_ROOT / "高中英语教材电子版" / "人教高中英语电子版教材（必修一至选修四）"
OUT_DIR = REPO_ROOT / "data" / "textbooks"


# --------------------------------------------------------------------------- #
# 书目录（单元标题 + 中文主题，与 2019 人教教材 CONTENTS 一一对应）
# --------------------------------------------------------------------------- #
BOOKS: list[dict] = [
    {
        "key": "必修一", "name": "人教版必修第一册", "grade": "高一",
        "pdf": "人教必修一英语电子版教材.pdf",
        "units": [
            ("Unit1 Teenage Life", "校园生活 · 社团与时间管理"),
            ("Unit2 Travelling Around", "旅行 · 行程规划与文化遗产"),
            ("Unit3 Sports and Fitness", "运动与健康 · 坚持与团队精神"),
            ("Unit4 Natural Disasters", "自然灾害 · 救援与重建"),
            ("Unit5 Languages Around the World", "世界语言 · 汉字与文化"),
        ],
    },
    {
        "key": "必修二", "name": "人教版必修第二册", "grade": "高一",
        "pdf": "人教必修二英语电子版教材.pdf",
        "units": [
            ("Unit1 Cultural Heritage", "文化遗产 · 保护与传承"),
            ("Unit2 Wildlife Protection", "野生动物保护 · 人与自然"),
            ("Unit3 The Internet", "互联网 · 数字生活"),
            ("Unit4 History and Traditions", "历史与传统 · 文化认同"),
            ("Unit5 Music", "音乐 · 艺术与情感"),
        ],
    },
    {
        "key": "必修三", "name": "人教版必修第三册", "grade": "高一",
        "pdf": "人教必修三英语电子版教材.pdf",
        "units": [
            ("Unit1 Festivals and Celebrations", "节日庆典 · 文化习俗"),
            ("Unit2 Morals and Virtues", "道德与美德 · 人生选择"),
            ("Unit3 Diverse Cultures", "多元文化 · 世界之窗"),
            ("Unit4 Space Exploration", "太空探索 · 科学与梦想"),
            ("Unit5 The Value of Money", "金钱的价值 · 人性与选择"),
        ],
    },
    {
        "key": "选一", "name": "人教版选择性必修第一册", "grade": "高二",
        "pdf": "人教选一英语电子版教材.pdf",
        "units": [
            ("Unit1 People of Achievement", "杰出人物 · 成就与价值"),
            ("Unit2 Looking into the Future", "展望未来 · 科技与生活"),
            ("Unit3 Fascinating Parks", "迷人公园 · 自然与人文"),
            ("Unit4 Body Language", "肢体语言 · 无声的交流"),
            ("Unit5 Working the Land", "耕耘大地 · 农业与奉献"),
        ],
    },
    {
        "key": "选二", "name": "人教版选择性必修第二册", "grade": "高二",
        "pdf": "人教选二英语电子版教材 .pdf",  # 文件名末尾带空格
        "units": [
            ("Unit1 Science and Scientists", "科学与科学家 · 求知与探索"),
            ("Unit2 Bridging Cultures", "文化桥梁 · 跨文化交流"),
            ("Unit3 Food and Culture", "饮食与文化 · 舌尖上的世界"),
            ("Unit4 Journey Across a Vast Land", "广袤大地之旅 · 铁路与山河"),
            ("Unit5 First Aid", "急救 · 生命守护"),
        ],
    },
    {
        "key": "选三", "name": "人教版选择性必修第三册", "grade": "高三",
        "pdf": "人教选三英语电子版教材.pdf",
        "units": [
            ("Unit1 Art", "艺术 · 审美与表达"),
            ("Unit2 Healthy Lifestyle", "健康生活 · 习惯与自律"),
            ("Unit3 Environmental Protection", "环境保护 · 绿色家园"),
            ("Unit4 Adversity and Courage", "逆境与勇气 · 坚持与成长"),
            ("Unit5 Poems", "诗歌 · 韵律与情感"),
        ],
    },
    {
        "key": "选四", "name": "人教版选择性必修第四册", "grade": "高三",
        "pdf": "人教选四英语电子版教材.pdf",
        "units": [
            ("Unit1 Science Fiction", "科幻 · 想象与未来"),
            ("Unit2 Iconic Attractions", "标志性景点 · 人文与自然"),
            ("Unit3 Sea Exploration", "海洋探索 · 资源与责任"),
            ("Unit4 Sharing", "分享 · 志愿服务"),
            ("Unit5 Launching Your Career", "生涯启航 · 职业规划"),
        ],
    },
]


# --------------------------------------------------------------------------- #
# 环境注入（复用 core.database / core.llm 的「环境变量优先、secrets 回落」）
# --------------------------------------------------------------------------- #
def _load_secrets_to_env() -> None:
    secrets_path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return
    data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
                 "LLM_BASE_URL", "LLM_MODEL", "LLM_VISION_MODEL"):
        value = data.get(name)
        if value:
            os.environ.setdefault(name, str(value))
    api_keys = data.get("LLM_API_KEYS")
    if api_keys and not os.environ.get("LLM_API_KEYS"):
        os.environ["LLM_API_KEYS"] = json.dumps([str(k) for k in api_keys], ensure_ascii=False)
    elif data.get("LLM_API_KEY") and not os.environ.get("LLM_API_KEY"):
        os.environ["LLM_API_KEY"] = str(data["LLM_API_KEY"])


_load_secrets_to_env()

import fitz  # noqa: E402  pymupdf
from core import llm  # noqa: E402

# --------------------------------------------------------------------------- #
# 分段工具
# --------------------------------------------------------------------------- #
_UNIT_MARK = re.compile(r"^\s*(Welcome\s+Unit|Unit\s*\d+)\s*$", re.MULTILINE)


def _segment_units(text: str) -> dict[int, str]:
    """把附录正文按 "Welcome Unit / Unit N" 分成 {编号: 文本}，Welcome Unit 编号为 -1。"""
    parts: dict[int, str] = {}
    matches = list(_UNIT_MARK.finditer(text))
    for idx, m in enumerate(matches):
        marker = m.group(1).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if marker.lower().startswith("welcome"):
            parts[-1] = body
        else:
            n = int(re.search(r"\d+", marker).group())
            parts[n] = body
    return parts


def _find_region(doc, starts_with: str, terminator: str) -> tuple[int, int] | None:
    """在书末附录里定位 [start_page, end_page)：从含 starts_with 的页开始，到含 terminator 的页结束。

    在书末 1/3 的页里查找，避免误命中目录/正文里的同名标题。
    """
    total = doc.page_count
    lo = int(total * 0.66)
    start = end = None
    for p in range(lo, total):
        t = doc[p].get_text()
        if start is None and starts_with in t:
            start = p
        if start is not None and terminator in t:
            end = p
            break
    if start is None or end is None:
        return None
    return start, end


# --------------------------------------------------------------------------- #
# 大模型结构化提示词
# --------------------------------------------------------------------------- #
_WORDS_SYSTEM = (
    "你是高中英语教材编辑。用户给出一本教材某单元的「生词表」文本（含英文单词、词性、中文释义，"
    "可能因换行错乱）。请把它整理成一个 JSON 数组，每个元素为 "
    '{"word": "英文单词或短语", "pos": "词性(如 n. / vt. / adj. / phr. / abbr.)", '
    '"explain": "中文释义"}。要求：1) 不遗漏任何词条、保持原顺序；2) word 只保留英文本身；'
    "3) 派生词/短语（如 sign up (for sth)）也作为独立词条。严格只输出 JSON 数组。"
)


_NOTES_SYSTEM = (
    "你是高中英语教材编辑。用户给出一本教材某单元的「Notes 注释」原始文本（每条含一个重点句型或短语、"
    "中文语法讲解、若干例句与例句翻译，可能因换行错乱）。请把它整理成一个 JSON 数组，每个元素为 "
    '{"pattern": "重点句型/短语(英文，含其中文讲解涉及的语法结构)", '
    '"explain": "中文语法讲解(精简)", '
    '"example": "一条英文例句", "translation": "该例句的中文翻译"}。'
    "要求：每条 Notes 生成一个元素，pattern 用英文原句，不要编造不存在的句型。严格只输出 JSON 数组。"
)

_PHONETIC = re.compile(r"/[^/\n]{1,80}/")

# 单词表确定性解析（不调大模型，快且准确）：
# 词条形如 "word /音标/ n. 中文释义"、"phrase 中文释义"（短语）、"Word 中文"（专有名词），
# 也有 word 单独一行、词性/释义换行、多词性续行（debate n. … / vt. & vi. …）等情况。
_POS_PAT = r"(?:vt|vi|v|n|adj|adv|prep|pron|conj|num|art|abbr|int|aux|phr)\."
_POS_AT_START = re.compile(rf"^({_POS_PAT}(?:\s*&\s*[a-z]+\.)?)\s*(.*)$")
_POS_AT_END = re.compile(rf"\s+({_POS_PAT}(?:\s*&\s*[a-z]+\.)?)\s*$")
_SKIP_LINE = re.compile(r"^(注[：:]|Words and Expressions|各单元|Appendices|Contents|\d+$)")


def _parse_words(raw: str) -> list[dict]:
    """把生词表文本确定性解析成 [{word, pos, explain}]。"""
    text = _PHONETIC.sub(" ", raw)
    text = re.sub(r"[ \t]+", " ", text)
    words: list[dict] = []
    last_word: str | None = None

    for line in text.splitlines():
        s = line.strip()
        if not s or _SKIP_LINE.match(s):
            continue
        # 中文续行（换行溢出的释义）
        if not re.match(r"^[A-Za-z]", s):
            if words:
                words[-1]["explain"] = (words[-1]["explain"] + s).strip()
            continue
        # 词性续行（同一词的另一个词性，如 debate vt. & vi.）
        pm = _POS_AT_START.match(s)
        if pm and last_word:
            words.append({"word": last_word, "pos": pm.group(1).strip(), "explain": pm.group(2).strip()})
            continue
        # 找首个中文字符，切出英文部分 / 中文释义
        cm = re.search(r"[一-鿿（]", s)
        if not cm:
            last_word = s  # 纯英文（word 单独一行，词性/释义在下一行）
            continue
        eng_part = s[:cm.start()].strip()
        explain = s[cm.start():].strip()
        # 从英文部分末尾解析词性（如 "ballet n."、"senior high school"）
        pm = _POS_AT_END.search(eng_part)
        if pm:
            head = eng_part[:pm.start()].strip()
            pos = pm.group(1).strip()
        else:
            head = eng_part.strip()
            pos = ""
        if not head:
            continue
        last_word = head
        words.append({"word": head, "pos": pos, "explain": explain})
    return words


def _structure_notes(raw: str) -> list[dict]:
    result = llm.structure(_NOTES_SYSTEM, raw, temperature=0.1, max_tokens=3000)
    if isinstance(result, dict):
        result = result.get("patterns") or result.get("items")
    if not isinstance(result, list):
        return []
    return [x for x in result if isinstance(x, dict) and x.get("pattern")]


# --------------------------------------------------------------------------- #
# 单元内容组装
# --------------------------------------------------------------------------- #
def _demo_knowledge(theme: str) -> dict:
    return {
        "vocab": {"summary": "本单元核心词汇与短语", "mastery": 0, "points": []},
        "grammar": {"summary": "本单元重点语法", "mastery": 0, "points": []},
        "discourse": {"summary": theme, "mastery": 0, "points": []},
    }


def extract_book(book: dict, use_llm: bool) -> dict:
    key = book["key"]
    pdf_path = PDF_DIR / book["pdf"]
    doc = fitz.open(str(pdf_path))
    print(f"\n=== 提取 {key}（{doc.page_count} 页）===")

    # 1) 单词表：Words and Expressions in Each Unit → Vocabulary
    word_region = _find_region(doc, "Words and Expressions in Each Unit", "Vocabulary")
    word_by_unit: dict[int, str] = {}
    if word_region:
        full = "\n".join(doc[p].get_text() for p in range(word_region[0], word_region[1] + 1))
        word_by_unit = _segment_units(full)
        print(f"  单词表区域 p{word_region[0]}~{word_region[1]}，分段：{sorted(k for k in word_by_unit if k >= 1)}")
    else:
        print("  [警告] 未定位到单词表区域")

    # 2) Notes → Grammar
    notes_region = _find_region(doc, "Notes", "Grammar")
    notes_by_unit: dict[int, str] = {}
    if notes_region:
        full = "\n".join(doc[p].get_text() for p in range(notes_region[0], notes_region[1] + 1))
        notes_by_unit = _segment_units(full)
        print(f"  Notes 区域 p{notes_region[0]}~{notes_region[1]}，分段：{sorted(k for k in notes_by_unit if k >= 1)}")
    else:
        print("  [警告] 未定位到 Notes 区域")

    units_out = []
    for num, (unit_title, theme) in enumerate(book["units"], 1):
        raw_words = word_by_unit.get(num, "")
        raw_notes = notes_by_unit.get(num, "")

        words = _parse_words(raw_words) if raw_words else []
        patterns = _structure_notes(raw_notes) if (use_llm and raw_notes) else []
        print(f"  {unit_title}: 单词 {len(words)} 个，句型 {len(patterns)} 条", flush=True)

        units_out.append({
            "unit": unit_title,
            "theme": theme,
            "words": words,
            "sentence_patterns": patterns,
            "passages": [],
            "knowledge": _demo_knowledge(theme),
            "vocab_stats": {"mastered": 0, "to_review": len(words)},
        })

    return {
        "key": key,
        "name": book["name"],
        "grade": book["grade"],
        "units": units_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="离线提取教材单词/句型为 JSON")
    parser.add_argument("--book", default=None, help="只提取某一册（key，如 必修一）")
    parser.add_argument("--all", action="store_true", help="提取全部 7 册")
    parser.add_argument("--no-llm", action="store_true", help="不调用大模型，只打印分段（调试用）")
    args = parser.parse_args()

    targets = BOOKS if args.all else [b for b in BOOKS if b["key"] == args.book]
    if not targets:
        print(f"[错误] 未知书 key：{args.book}，可选 {[b['key'] for b in BOOKS]}", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for book in targets:
        data = extract_book(book, use_llm=not args.no_llm)
        if args.no_llm:
            continue
        out_path = OUT_DIR / f"{book['key']}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → 写入 {out_path.relative_to(REPO_ROOT)}")

    if not args.no_llm:
        _write_index()
        print(f"\n已生成 {len(_load_index_from_disk())} 册 → data/textbooks/")

    return 0


def _load_index_from_disk() -> list[dict]:
    """从磁盘上已有的 <key>.json 文件生成书目录（单书重跑不覆盖全量索引）。"""
    return [
        {"key": b["key"], "name": b["name"], "grade": b["grade"], "units": [u[0] for u in b["units"]]}
        for b in BOOKS if (OUT_DIR / f"{b['key']}.json").exists()
    ]


def _write_index() -> None:
    index = _load_index_from_disk()
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
