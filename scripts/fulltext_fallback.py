#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 全文兜底：对 zotero_fulltext.json 中正文为空的条目，
用内置 nature-paper-card/scripts/prepare_paper.py 从同一 PDF 抽取逐页正文。

本脚本不做 PDF 解析本身，只负责：定位 PDF → 调用内置 prepare_paper.py →
把 pages[].text 拼回 zotero_fulltext.json 的 text 字段 → 记录来源与页码。

用法（路径请替换为本机实际目录）：
  python scripts/fulltext_fallback.py \
    --fulltext "<输出目录>\\zotero_fulltext.json" \
    --pdf-dir  "<PDF 所在目录>" \
    --workdir  "<工作目录>\\paper-card-work" \
    [--force]      # 即使 text 非空也重抽
    [--only 文件名.pdf]

输出：
  <workdir>/<条目序号>-<文件名>/source_bundle.json
  <workdir>/<条目序号>-<文件名>/rendered-pages/page-0NN.png
  并就地更新 --fulltext 指定的 JSON（新增 textSource / pdfPages 字段）

注意：textSource=pdf_extraction 属于偏差，B 阶段必须在笔记「分析范围说明」中声明。
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PREPARE = SCRIPT_DIR.parent / "nature-paper-card" / "scripts" / "prepare_paper.py"


def safe_stem(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r'[\\/:*?"<>|]+', "_", stem)[:60] or "paper"


def run_prepare(pdf: Path, workdir: Path) -> dict:
    """调用内置 prepare_paper.py；返回 bundle 字典。失败抛出 RuntimeError。"""
    if not PREPARE.exists():
        raise RuntimeError(f"找不到内置 prepare_paper.py：{PREPARE}")
    out_dir = workdir / f"{safe_stem(pdf.name)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / "source_bundle.json"
    cmd = [
        sys.executable, str(PREPARE), str(pdf),
        "--output", str(bundle_path),
        "--render-dir", str(out_dir / "rendered-pages"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(proc.stdout.strip())
    if proc.returncode != 0 or not bundle_path.exists():
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:600] or "prepare_paper.py 失败")
    return json.loads(bundle_path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="A2 全文兜底（调用内置 prepare_paper.py）")
    ap.add_argument("--fulltext", required=True, help="A 阶段导出的 zotero_fulltext.json")
    ap.add_argument("--pdf-dir", required=True, help="PDF 所在目录")
    ap.add_argument("--workdir", required=True, help="source_bundle 与渲染页的落盘目录")
    ap.add_argument("--force", action="store_true", help="text 非空也重抽")
    ap.add_argument("--only", default=None, help="只处理指定文件名")
    args = ap.parse_args()

    data = json.loads(Path(args.fulltext).read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    pdf_dir = Path(args.pdf_dir)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    done, skipped, failed = [], [], []
    for entry in entries:
        name = entry.get("filename") or ""
        if args.only and args.only not in name:
            continue
        if (entry.get("textChars") or 0) > 0 and entry.get("text") and not args.force:
            skipped.append(name)
            continue
        pdf = pdf_dir / name
        if not pdf.exists():
            failed.append({"file": name, "error": f"PDF 不存在：{pdf}"})
            continue
        try:
            bundle = run_prepare(pdf, workdir)
            pages = bundle.get("pages") or []
            text = "".join(
                f"\n===== PDF PAGE {p.get('pdf_page')} (printed {p.get('printed_page')}) =====\n"
                + (p.get("text") or "")
                for p in pages
            )
            if not text.strip():
                failed.append({"file": name, "error": "抽取到 0 字符：可能为扫描件，需 OCR"})
                continue
            entry["text"] = text
            entry["textChars"] = len(text)
            entry["truncated"] = False
            entry["textSource"] = "pdf_extraction"
            entry["pdfPages"] = bundle.get("page_count") or len(pages)
            entry["locatorMode"] = (bundle.get("validation") or {}).get("locator_mode") or "page-grounded"
            done.append(f"{name}（{entry['pdfPages']} 页 / {entry['textChars']} 字符）")
        except Exception as e:  # 单篇失败不中断整批
            failed.append({"file": name, "error": str(e)})

    Path(args.fulltext).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== A2 兜底汇总 =====")
    print(f"已抽取：{len(done)}　跳过（已有正文）：{len(skipped)}　失败：{len(failed)}")
    for d in done:
        print(f"  [PDF] {d}")
    if failed:
        print("失败清单：")
        for f in failed:
            print(f"  - {f['file']}: {f['error']}")
    if done:
        print("\n提醒：textSource=pdf_extraction 属偏差，B 阶段须在笔记「分析范围说明」节声明；"
              "表格列结构须看 rendered-pages 逐页核对。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
