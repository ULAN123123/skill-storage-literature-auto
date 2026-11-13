#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zotero-paper-notes · Local API 直连脚本（Zotero 10+，Windows 本机）

功能：
  ping          探测本地 API 是否开启、列出分类
  import-export 扫描 PDF 目录 → 在目标分类下建父条目 → 三阶段上传 PDF → 导出全文 JSON
  write-notes   读取 notes JSON，按条目 key 创建/更新 paper-card 子笔记

只使用 Python 标准库，无需 pip 安装。

前置条件：
  1. Zotero 10+ 已安装并运行；
  2. 设置 → 高级 → 勾选「允许此计算机上的其他应用程序与 Zotero 通讯」；
  3. 首次写入时 Zotero 会弹授权窗，选「始终允许」可只弹一次。

示例（路径请替换为本机实际目录）：
  python zotero_local_api.py ping
  python zotero_local_api.py import-export --pdf-dir "<PDF 所在目录>" --collection reference
  python zotero_local_api.py write-notes --notes "<输出目录>\\zotero_notes.json"
"""

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:23119"
USER_PREFIX = "/api/users/0"
APP_NAME = "zotero-paper-notes"
NOTE_TAG = "paper-card"
AUTH_FILE = Path(__file__).resolve().parent / ".zotero_local_auth.json"
MAX_TEXT_CHARS = 150000


# ---------- 基础 HTTP ----------

class ApiError(Exception):
    def __init__(self, code, body):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}: {body}")


# 本地回环请求必须绕过系统代理，否则可能被代理拦截导致 10061
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(method, path, body=None, headers=None, raw=None, timeout=120):
    url = BASE + path
    data = None
    h = dict(headers or {})
    if raw is not None:
        data = raw
        h.setdefault("Content-Type", "application/octet-stream")
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", "replace")
            try:
                payload = json.loads(payload) if payload else None
            except json.JSONDecodeError:
                pass
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            pass
        return e.code, dict(e.headers or {}), payload
    except urllib.error.URLError as e:
        raise SystemExit(
            f"连不上 Zotero 本地接口 {BASE}。请确认 Zotero 已运行、"
            f"且「允许此计算机上的其他应用程序与 Zotero 通讯」已开启。原始错误：{e.reason}"
        )


def _header(headers, name):
    if not headers:
        return None
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def get_server_id():
    _, headers, _ = _request("GET", "/api/")
    sid = _header(headers, "Zotero-Server-ID")
    if not sid:
        raise SystemExit("响应头缺少 Zotero-Server-ID，无法继续写请求。")
    return sid


def _load_auth():
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_auth(auth):
    AUTH_FILE.write_text(json.dumps(auth, ensure_ascii=False, indent=2), encoding="utf-8")


def authorize():
    sid = get_server_id()
    code, _, body = _request(
        "POST", "/api/local/authorize",
        body={"appName": APP_NAME},
        headers={"Zotero-Server-ID": sid},
    )
    if code == 403:
        raise SystemExit("你在 Zotero 授权窗选择了拒绝，无法写入。")
    if code != 200 or not isinstance(body, dict) or not body.get("key"):
        raise SystemExit(f"授权失败 HTTP {code}: {body}")
    auth = {"key": body["key"], "remember": bool(body.get("remember")), "serverID": sid}
    _save_auth(auth)
    print(f"[授权] 已获取本地写入 key（remember={auth['remember']}）")
    return auth


def _ensure_auth():
    auth = _load_auth()
    if not auth.get("key"):
        auth = authorize()
    return auth


def write(method, path, body=None, raw=None, extra_headers=None):
    """带授权头与 Server-ID 的写请求；遇到 401 重新授权一次。"""
    auth = _ensure_auth()
    sid = auth.get("serverID") or get_server_id()
    token = uuid.uuid4().hex[:16]

    def _do(key):
        headers = {
            "Zotero-Server-ID": sid,
            "Zotero-API-Key": key,
            "Zotero-Write-Token": token,
        }
        if extra_headers:
            headers.update(extra_headers)
        return _request(method, path, body=body, raw=raw, headers=headers)

    code, headers, resp = _do(auth["key"])
    if code == 401:
        auth = authorize()
        code, headers, resp = _do(auth["key"])
    if code >= 400:
        raise ApiError(code, resp)
    return code, headers, resp


# ---------- 分类 ----------

def list_collections():
    _, _, body = _request("GET", f"{USER_PREFIX}/collections")
    if not isinstance(body, list):
        raise SystemExit(f"分类列表返回异常：{body}")
    return body


def find_collection(name):
    cols = list_collections()
    for c in cols:
        # Zotero API v3 把分类名放在顶层对象的 data.name 下；兼容旧结构的顶层 name
        nm = (c.get("data") or {}).get("name") or c.get("name", "")
        if str(nm).strip().lower() == name.strip().lower():
            return c
    return None


def ensure_collection(name, create_if_missing=True):
    col = find_collection(name)
    if col:
        return col["key"], False
    if not create_if_missing:
        names = [((c.get("data") or {}).get("name") or c.get("name")) for c in list_collections()]
        raise SystemExit(f"找不到分类「{name}」。现有分类：{', '.join(str(n) for n in names)}")
    _, _, resp = write("POST", f"{USER_PREFIX}/collections", body=[{"name": name}])
    success = _as_list((resp or {}).get("successful")) or _as_list((resp or {}).get("success"))
    if not success:
        raise SystemExit(f"新建分类失败：{resp}")
    return success[0]["key"], True


# ---------- 条目创建 ----------

def _as_list(node):
    """Zotero 本地 API 的 successful/failed 可能是数组，也可能是 {"0": {...}} 对象。"""
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return node
    return []


def _batch_items(items):
    _, _, resp = write("POST", f"{USER_PREFIX}/items", body=items)
    success = _as_list((resp or {}).get("successful"))
    failed = _as_list((resp or {}).get("failed"))
    if failed:
        for f in failed:
            print(f"  [警告] 条目写入失败：{f}", file=sys.stderr)
    return success


def create_parent(title, coll_key, extra_tags=None):
    tags = [{"tag": t} for t in (extra_tags or [])]
    items = [{
        "itemType": "document",
        "title": title,
        "collections": [coll_key],
        "tags": tags,
    }]
    success = _batch_items(items)
    if not success:
        raise ApiError(500, "父条目未创建成功")
    return success[0]["key"]


def create_attachment(parent_key, filename, coll_key):
    items = [{
        "itemType": "attachment",
        "linkMode": "imported_file",
        "parentItem": parent_key,
        "contentType": "application/pdf",
        "title": filename,
    }]
    success = _batch_items(items)
    if not success:
        raise ApiError(500, "附件条目未创建成功")
    return success[0]["key"]


# ---------- 文件三阶段上传 ----------

def upload_pdf(att_key, pdf_path: Path):
    data = pdf_path.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    filesize = len(data)
    mtime = int(pdf_path.stat().st_mtime * 1000)
    filename = pdf_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"

    # 阶段 1：申请上传（参数放表单 body，按 Web API 规范）
    form1 = urllib.parse.urlencode({
        "md5": md5, "filename": filename, "filesize": filesize, "mtime": mtime,
    }).encode("utf-8")
    code, _, body = write(
        "POST", f"{USER_PREFIX}/items/{att_key}/file",
        raw=form1,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded",
                       "If-None-Match": "*"},
    )
    if isinstance(body, dict) and body.get("exists") == 1:
        print("  文件已存在，跳过上传")
        return
    if code != 200 or not isinstance(body, dict) or not body.get("url"):
        raise ApiError(code, f"阶段1上传申请失败：{body}")

    # 阶段 2：上传字节 = prefix + 文件 + suffix；url 只取 path+query 重新拼到 BASE
    upload_url = body["url"]
    up = urllib.parse.urlparse(upload_url)
    up_path = up.path + (("?" + up.query) if up.query else "")
    prefix = (body.get("prefix") or "").encode("utf-8")
    suffix = (body.get("suffix") or "").encode("utf-8")
    payload = prefix + data + suffix
    ct = body.get("contentType") or content_type
    code, _, _ = _request("POST", up_path, raw=payload, headers={"Content-Type": ct})
    if code not in (200, 201):
        raise ApiError(code, "阶段2文件字节上传失败")

    # 阶段 3：登记落盘（upload 参数放表单 body）
    form3 = urllib.parse.urlencode({"upload": body["uploadKey"]}).encode("utf-8")
    code, _, _ = write(
        "POST", f"{USER_PREFIX}/items/{att_key}/file",
        raw=form3,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded",
                       "If-None-Match": "*"},
    )
    if code != 204:
        raise ApiError(code, f"阶段3登记上传失败（HTTP {code}）")


# ---------- 全文 ----------

def fetch_fulltext(att_key):
    code, _, body = _request("GET", f"{USER_PREFIX}/items/{att_key}/fulltext")
    if code != 200 or not isinstance(body, dict):
        return ""
    return body.get("content") or body.get("text") or ""


def fetch_item(item_key):
    code, _, body = _request("GET", f"{USER_PREFIX}/items/{item_key}")
    return body if code == 200 else None


def fetch_children(parent_key):
    code, _, body = _request("GET", f"{USER_PREFIX}/items/{parent_key}/children")
    return body if code == 200 and isinstance(body, list) else []


# ---------- 子命令 ----------

def cmd_ping(_args):
    code, headers, body = _request("GET", "/api/")
    if code == 403:
        raise SystemExit("本地 API 未开启：设置 → 高级 → 勾选「允许此计算机上的其他应用程序与 Zotero 通讯」。")
    sid = _header(headers, "Zotero-Server-ID")
    ver = _header(headers, "Zotero-API-Version")
    print(f"连接正常：API v{ver}，Server-ID={sid}")
    cols = list_collections()
    print(f"共 {len(cols)} 个分类：")
    for c in cols:
        nm = (c.get("data") or {}).get("name") or c.get("name")
        print(f"  - {nm}  (key={c.get('key')})")


def cmd_import_export(args):
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.is_dir():
        raise SystemExit(f"PDF 目录不存在：{pdf_dir}")
    coll_key, created = ensure_collection(args.collection, create_if_missing=True)
    print(f"目标分类：{args.collection}（key={coll_key}，{'新建' if created else '已有'}）")

    pdfs = sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        raise SystemExit(f"目录下没有 PDF：{pdf_dir}")
    print(f"发现 {len(pdfs)} 个 PDF")

    entries, failures, no_text = [], [], []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name}")
        try:
            title = pdf.stem
            parent_key = create_parent(title, coll_key, extra_tags=["paper-imported"])
            att_key = create_attachment(parent_key, pdf.name, coll_key)
            upload_pdf(att_key, pdf)

            text = fetch_fulltext(att_key)
            truncated = len(text) > MAX_TEXT_CHARS
            text_out = text[:MAX_TEXT_CHARS]
            if not text_out:
                no_text.append(pdf.name)

            parent = fetch_item(parent_key) or {}
            entries.append({
                "key": parent_key,
                "attachmentKey": att_key,
                "title": parent.get("title") or title,
                "filename": pdf.name,
                "year": parent.get("date", ""),
                "authors": [c.get("lastName") or c.get("name", "") for c in (parent.get("creators") or [])],
                "textChars": len(text),
                "truncated": truncated,
                "text": text_out,
            })
        except Exception as e:
            failures.append({"file": pdf.name, "error": str(e)})
            print(f"  [失败] {e}", file=sys.stderr)

    out = Path(args.out_json)
    out.write_text(json.dumps({
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "collection": args.collection,
        "count": len(entries),
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 汇总 =====")
    print(f"成功：{len(entries)}　失败：{len(failures)}　无正文：{len(no_text)}")
    if no_text:
        print("无正文（可能是扫描件，需 OCR）：")
        for n in no_text:
            print(f"  - {n}")
    if failures:
        print("失败清单：")
        for f in failures:
            print(f"  - {f['file']}: {f['error']}")
    print(f"全文 JSON 已写出：{out}")


def cmd_write_notes(args):
    notes_path = Path(args.notes)
    notes = json.loads(notes_path.read_text(encoding="utf-8"))
    if not isinstance(notes, list):
        raise SystemExit("notes JSON 顶层必须是数组")

    stats = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    failures = []

    for n in notes:
        key = n.get("key")
        html = n.get("html")
        if not key or not html:
            stats["failed"] += 1
            failures.append({"key": key, "error": "缺少 key 或 html"})
            continue
        try:
            parent = fetch_item(key)
            if not parent:
                raise ApiError(404, f"找不到条目 key={key}")

            children = fetch_children(key)
            existing_note = None
            for ch in children:
                data = ch.get("data") or ch
                if data.get("itemType") != "note":
                    continue
                tags = [t.get("tag") if isinstance(t, dict) else t for t in (data.get("tags") or [])]
                if NOTE_TAG in tags:
                    existing_note = ch
                    break

            tags = [{"tag": NOTE_TAG}]
            for t in (n.get("tags") or []):
                if t != NOTE_TAG:
                    tags.append({"tag": t})

            if existing_note:
                if not args.update_existing:
                    stats["skipped"] += 1
                    continue
                ver = (existing_note.get("data") or existing_note).get("version")
                write("PUT", f"{USER_PREFIX}/items/{existing_note['key']}",
                      body={"itemType": "note", "parentItem": key, "note": html, "tags": tags},
                      extra_headers={"If-Unmodified-Since-Version": str(ver)})
                stats["updated"] += 1
            else:
                _batch_items([{
                    "itemType": "note",
                    "parentItem": key,
                    "note": html,
                    "tags": tags,
                }])
                stats["created"] += 1
        except Exception as e:
            stats["failed"] += 1
            failures.append({"key": key, "title": n.get("title"), "error": str(e)})
            print(f"  [失败] {key}: {e}", file=sys.stderr)

    print("\n===== 汇总 =====")
    print(f"新建笔记：{stats['created']}　更新：{stats['updated']}　跳过：{stats['skipped']}　失败：{stats['failed']}")
    if failures:
        print("失败清单：")
        for f in failures:
            print(f"  - {f.get('key')} {f.get('title','')}: {f['error']}")


def main():
    parser = argparse.ArgumentParser(description="Zotero Local API 批量导入与写笔记")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help="探测 API 并列分类")
    p_ping.set_defaults(func=cmd_ping)

    p_imp = sub.add_parser("import-export", help="导入 PDF 并导出全文 JSON")
    p_imp.add_argument("--pdf-dir", required=True, help="PDF 所在本机目录")
    p_imp.add_argument("--collection", default="reference", help="目标分类名，默认 reference")
    p_imp.add_argument("--out-json", default="zotero_fulltext.json", help="导出 JSON 路径")
    p_imp.set_defaults(func=cmd_import_export)

    p_wr = sub.add_parser("write-notes", help="把总结写回为子笔记")
    p_wr.add_argument("--notes", required=True, help="zotero_notes.json 路径")
    p_wr.add_argument("--update-existing", action="store_true", default=True, help="更新已有 paper-card 笔记")
    p_wr.add_argument("--no-update-existing", dest="update_existing", action="store_false")
    p_wr.set_defaults(func=cmd_write_notes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
