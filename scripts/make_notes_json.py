#!/usr/bin/env python3
"""把 Paper Card 的 Markdown 转成 Zotero 子笔记 JSON（HTML）。

Zotero 笔记只接受 HTML，不接受 Markdown；本脚本负责转换并组装 zotero_notes.json。

用法：
  python scripts/make_notes_json.py --card paper-card.md --key ABCD2345 --out zotero_notes.json
  python scripts/make_notes_json.py --card paper-card.md --key ABCD2345 --out zotero_notes.json --merge

参数：
  --card    Paper Card 的 .md 文件
  --key     A 阶段 JSON 里的条目 key（父条目 key，不得改写）
  --out     输出 JSON 路径
  --title   笔记标题；缺省时取 Markdown 第一个一级标题
  --tags    逗号分隔的标签，默认 paper-card
  --merge   输出文件已存在时合并：按 key 替换，不重复追加

依赖：pip install markdown
"""

import argparse
import json
import re
from pathlib import Path

import markdown


def first_h1(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Paper Card"


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper Card Markdown → Zotero 笔记 JSON")
    parser.add_argument("--card", required=True, help="Paper Card 的 Markdown 路径")
    parser.add_argument("--key", required=True, help="Zotero 父条目 key")
    parser.add_argument("--out", required=True, help="输出 zotero_notes.json 路径")
    parser.add_argument("--title", default=None, help="笔记标题，默认取第一个一级标题")
    parser.add_argument("--tags", default="paper-card", help="逗号分隔标签，默认 paper-card")
    parser.add_argument("--merge", action="store_true", help="与已有 JSON 合并（同 key 替换）")
    args = parser.parse_args()

    md_text = Path(args.card).read_text(encoding="utf-8")
    html = markdown.markdown(md_text, extensions=["tables", "sane_lists", "nl2br"])

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] or ["paper-card"]
    item = {
        "key": args.key,
        "title": args.title or first_h1(md_text),
        "html": html,
        "tags": tags,
    }

    out_path = Path(args.out)
    notes = []
    if args.merge and out_path.exists():
        notes = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(notes, list):
            raise SystemExit("已有 JSON 顶层不是数组，拒绝合并")
        notes = [n for n in notes if n.get("key") != args.key]

    notes.append(item)
    out_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    # 结构自检：16 个二级标题、至少 1 张表
    h2 = len(re.findall(r"<h2>", html))
    tables = html.count("<table>")
    print(f"wrote {out_path} | key={args.key} md_chars={len(md_text)} "
          f"html_chars={len(html)} h2={h2} tables={tables} notes_in_file={len(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
