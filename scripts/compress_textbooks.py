"""压缩教材数据：去掉 JSON 缩进空白与空/样板字段，不改动任何教材知识。

只做三件事（全部无损）：
1. 紧凑输出（无缩进，ensure_ascii=False，中文保留原文）；
2. 删除恒为空的 passages / knowledge（points 全空、summary 为固定模板）；
3. 删除恒为 0 的 vocab_stats.mastered，保留 to_review（复习页展示「待巩固词汇」用）。

保留字段：key/name/grade、unit/theme、words(word/pos/explain)、
         sentence_patterns(pattern/explain/example/translation)、vocab_stats.to_review。

用法：python scripts/compress_textbooks.py
幂等：可重复执行，已压缩的文件再跑一次结果不变。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "textbooks"

# 每册教材需要剔除的字段（全部为空或样板，不含知识）
UNIT_DROP_FIELDS = ("passages", "knowledge")


def _compress_book(data: dict) -> dict:
    """剔除空/样板字段，返回精简后的单册结构。"""
    units = []
    for u in data.get("units", []):
        unit = {k: v for k, v in u.items() if k not in UNIT_DROP_FIELDS}
        # vocab_stats 只保留 to_review，mastered 恒为 0
        vs = u.get("vocab_stats") or {}
        unit["vocab_stats"] = {"to_review": vs.get("to_review", 0)}
        units.append(unit)
    return {
        "key": data.get("key", ""),
        "name": data.get("name", ""),
        "grade": data.get("grade", ""),
        "units": units,
    }


def _dump(obj) -> bytes:
    """紧凑序列化：无缩进、中文不转义、最小分隔符。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def main() -> None:
    total_before = total_after = 0

    # index.json：仅紧凑化（无空字段）
    index_path = DATA_DIR / "index.json"
    index_before = index_path.stat().st_size
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    index_path.write_bytes(_dump(index_data))
    index_after = index_path.stat().st_size
    total_before += index_before
    total_after += index_after
    print(f"index.json        {index_before/1024:6.1f} KB -> {index_after/1024:6.1f} KB")

    # 7 册教材：紧凑化 + 剔除空/样板字段
    for key in [b["key"] for b in index_data]:
        path = DATA_DIR / f"{key}.json"
        before = path.stat().st_size
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_bytes(_dump(_compress_book(data)))
        after = path.stat().st_size
        total_before += before
        total_after += after
        print(f"{key}.json  {before/1024:6.1f} KB -> {after/1024:6.1f} KB")

    print("-" * 40)
    print(f"合计              {total_before/1024:6.1f} KB -> {total_after/1024:6.1f} KB"
          f"（减小 {100 - total_after/total_before*100:.1f}%）")


if __name__ == "__main__":
    main()
