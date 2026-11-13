#!/usr/bin/env python3
"""把被误改成独立笔记的 paper-card 笔记重新挂回指定父条目。

背景：Zotero Local API 的 PUT 是整项替换；更新时若漏传 parentItem，
子笔记会变成库里的独立笔记（父条目下看不到）。
本脚本读取现有 HTML 与标签，补回 parentItem 后写回。

用法：
  python scripts/reattach_note.py --note XYZ12345 --parent ABCD2345
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zotero_local_api as z


def main() -> int:
    parser = argparse.ArgumentParser(description="把笔记重新挂回父条目")
    parser.add_argument("--note", required=True, help="笔记条目 key")
    parser.add_argument("--parent", required=True, help="目标父条目 key")
    args = parser.parse_args()

    code, _, body = z._request("GET", f"{z.USER_PREFIX}/items/{args.note}")
    data = body.get("data") if isinstance(body, dict) else None
    if not data:
        raise SystemExit(f"读取 {args.note} 失败：{body}")
    if data.get("itemType") != "note":
        raise SystemExit(f"{args.note} 不是 note（itemType={data.get('itemType')}）")

    parent = z.fetch_item(args.parent)
    if not parent:
        raise SystemExit(f"父条目不存在：{args.parent}")

    tags = data.get("tags") or [{"tag": "paper-card"}]
    print(f"before parentItem={data.get('parentItem')} version={data.get('version')} chars={len(data.get('note',''))}")

    z.write("PUT", f"{z.USER_PREFIX}/items/{args.note}",
            body={
                "itemType": "note",
                "parentItem": args.parent,
                "note": data.get("note") or "",
                "tags": tags,
            },
            extra_headers={"If-Unmodified-Since-Version": str(data["version"])})

    code, _, body = z._request("GET", f"{z.USER_PREFIX}/items/{args.note}")
    after = body.get("data") if isinstance(body, dict) else {}
    print(f"after  parentItem={after.get('parentItem')} version={after.get('version')} chars={len(after.get('note',''))}")
    return 0 if after.get("parentItem") == args.parent else 1


if __name__ == "__main__":
    raise SystemExit(main())
