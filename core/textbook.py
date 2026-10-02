"""教材内容层：从 data/textbooks/*.json 加载 7 册教材的单元内容。

- 教材内容为静态参考数据（教材单词、重点句型、课文），由 scripts/extract_textbooks.py 离线生成；
- 题目（练习题/模拟题）为动态数据，在 MySQL 的 question_bank 中，不在本层；
- JSON 缺失时返回空，由 tutor_ai 回退到内置演示内容，避免启动崩溃。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "textbooks"

_index: list[dict] | None = None
_book_cache: dict[str, dict | None] = {}


def _load_index() -> list[dict]:
    """读取书目录 index.json，失败/缺失返回空列表。"""
    global _index
    if _index is None:
        try:
            raw = json.loads((DATA_DIR / "index.json").read_text(encoding="utf-8"))
            _index = raw if isinstance(raw, list) else []
        except (OSError, ValueError):
            _index = []
    return _index


def get_books() -> list[dict]:
    """全部教材（按 index.json 顺序），每项含 key/name/grade/units。"""
    return _load_index()


def get_book_keys() -> list[str]:
    """全部教材 key，如 ['必修一', '必修二', ..., '选四']。"""
    return [b.get("key", "") for b in get_books() if b.get("key")]


def get_book(key: str) -> dict | None:
    """单册完整内容（含 units 详情）；缺失返回 None。"""
    if key in _book_cache:
        return _book_cache[key]
    data: dict | None = None
    try:
        raw = json.loads((DATA_DIR / f"{key}.json").read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    except (OSError, ValueError):
        data = None
    _book_cache[key] = data
    return data


def get_book_meta(key: str) -> dict | None:
    """书目录元信息（name/grade/units 列表）。"""
    for b in get_books():
        if b.get("key") == key:
            return b
    return None


def get_units(key: str) -> list[str]:
    """某册书的单元名列表，如 ['Unit1 Teenage Life', ...]。"""
    book = get_book(key)
    if not book:
        return []
    return [u.get("unit", "") for u in book.get("units", []) if u.get("unit")]


def get_unit_content(key: str, unit: str) -> dict | None:
    """某册书某单元的完整内容；缺失返回 None。"""
    book = get_book(key)
    if not book:
        return None
    for u in book.get("units", []):
        if u.get("unit") == unit:
            return u
    return None


def get_default_book() -> dict | None:
    """默认书（index 第一本）。"""
    books = get_books()
    return books[0] if books else None
