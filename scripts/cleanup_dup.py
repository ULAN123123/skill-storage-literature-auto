#!/usr/bin/env python3
"""排查并清理同一父条目下重复的 paper-card 子笔记。

背景：早期版本的 write-notes 读不到 data 包装层，重复运行会重复新建笔记。
本脚本只处理「同一父条目 + 同一标签」的重复笔记，默认只列出，不删除。

用法：
  # 只查看
  python scripts/cleanup_dup.py --parent ABCD2345

  # 删掉指定的一条
  python scripts/cleanup_dup.py --parent ABCD2345 --delete XYZ12345

  # 自动去重：同标签多条时保留 version 最大（最新）的一条
  python scripts/cleanup_dup.py --parent ABCD2345 --dedupe
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zotero_local_api as z


def note_children(parent_key):
    rows = []
    for ch in z.fetch_children(parent_key):
        data = ch.get("data") or ch
        if data.get("itemType") != "note":
            continue
        tags = [t.get("tag") if isinstance(t, dict) else t for t in (data.get("tags") or [])]
        rows.append({
            "key": ch.get("key") or data.get("key"),
            "version": data.get("version", 0),
            "chars": len(data.get("note") or ""),
            "tags": tags,
            "parentItem": data.get("parentItem"),
        })
    return rows


def delete_note(note_key: str):
    code, headers, body = z._request("GET", f"{z.USER_PREFIX}/items/{note_key}")
    data = body.get("data") if isinstance(body, dict) else None
    if not data:
        raise SystemExit(f"读取 {note_key} 失败：{body}")
    z.write("DELETE", f"{z.USER_PREFIX}/items/{note_key}",
            extra_headers={"If-Unmodified-Since-Version": str(data["version"])})
    print(f"deleted {note_key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="清理重复 paper-card 子笔记")
    parser.add_argument("--parent", required=True, help="父条目 key")
    parser.add_argument("--tag", default="paper-card", help="标签，默认 paper-card")
    parser.add_argument("--delete", default=None, help="要删除的笔记 key")
    parser.add_argument("--dedupe", action="store_true", help="同标签多条时保留最新一条，删除其余")
    args = parser.parse_args()

    rows = [r for r in note_children(args.parent) if args.tag in r["tags"]]
    print(f"parent={args.parent} tag={args.tag} matched={len(rows)}")
    for r in rows:
        print(f"  {r['key']} version={r['version']} chars={r['chars']} parent={r['parentItem']}")

    if args.delete:
        if args.delete not in {r["key"] for r in rows}:
            print(f"{args.delete} 不在该父条目的 {args.tag} 笔记中，拒绝删除")
            return 1
        delete_note(args.delete)
    elif args.dedupe and len(rows) > 1:
        keep = max(rows, key=lambda r: r["version"])
        print(f"keep {keep['key']} (version={keep['version']})")
        for r in rows:
            if r["key"] != keep["key"]:
                delete_note(r["key"])
    elif len(rows) > 1:
        print("存在重复，但未指定 --delete 或 --dedupe，未做任何删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
