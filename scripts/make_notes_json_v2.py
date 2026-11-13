#!/usr/bin/env python3
"""Paper Card Markdown -> Zotero 子笔记 JSON（HTML），带公式/上下标渲染。

与旧版 `make_notes_json.py` 参数兼容，可直接替换。新增两种用法：

  1) 生成：Markdown -> JSON
     python make_notes_json_v2.py --card paper-card.md --key ABCD2345 --out zotero_notes.json [--merge]

  2) 存量修复：就地改写已生成 JSON 里的 html（不必重新做精读）
     python make_notes_json_v2.py --notes zotero_notes.json [--out zotero_notes_fixed.json]

渲染依据（Zotero note-editor 官方 schema，已核对源码）：
    行内公式  ->  <span class="math">$LATEX$</span>
    行间公式  ->  <pre class="math">$$LATEX$$</pre>
Zotero 用 KaTeX 渲染这两个节点；不要塞 MathJax/KaTeX 的 HTML 输出（会被当纯文本或剥掉）。

裸上下标（I_V、D'_T、r^{(t)}_c、10^6）转成 <sub>/<sup>，避免 `_` `^` 原样显示。

依赖：pip install markdown
"""

import argparse
import html as html_lib
import json
import re
from pathlib import Path

import markdown

# ---------------------------------------------------------------- 数学片段识别

MATH_PAT = re.compile(
    r"(?<!\\)\$\$(?P<display>.+?)\$\$"          # $$...$$ 行间
    r"|(?<!\\)\$(?P<inline>[^\$\n]+?)\$"        # $...$ 行内
    r"|\\\[(?P<bdisplay>.+?)\\\]"               # \[...\]
    r"|\\\((?P<binline>.+?)\\\)"                # \(...\)
    , re.S)

LETTER = r"[A-Za-z\u0370-\u03ff*]"          # 拉丁 + 希腊字母（δ、α 等）
SAFE_LATEX = re.compile(r"^[A-Za-z0-9_^{}()+*/=<>|.,\-:\u0370-\u03ff\u2208\u222a\u2229\u2264\u2265 ]+$")

# 组合式：X^{(t)}_{c} —— 整段交给 KaTeX 渲染，避免 sup 后面挂裸下标
COMBINED = re.compile(
    rf"(?<![\w\\])({LETTER}[A-Za-z0-9*']{{0,3}})\^\{{([^{{}}\n]{{1,16}})\}}_\{{?([A-Za-z0-9]{{1,4}})\}}?")
SUB_BRACE = re.compile(rf"(?<![\w\\])({LETTER}[A-Za-z0-9*']{{0,4}})(?:_|\*)\{{([^{{}}\n]{{1,24}})\}}")
SUP_BRACE = re.compile(rf"(?<![\w\\])([A-Za-z0-9]{{1,4}})\^\{{([^{{}}\n]{{1,24}})\}}")
# 裸下标：基名单字符（f_CLIP / r_c）或 2-4 字符且含大写（LLM_T / M_R / A*_q）
SUB_BARE = re.compile(rf"(?<![\w\\])({LETTER}[A-Za-z*']{{0,3}})_([A-Za-z0-9]{{1,4}})(?![\w])")
SUP_BARE = re.compile(r"(?<![\w\\])([A-Za-z0-9]{1,2})\^([A-Za-z0-9]{1,3})(?![\w])")

SOURCE_TAG = re.compile(r"\[(Paper:[^\]\n]{0,90}|Analysis)\]")


def _base_ok(base: str) -> bool:
    """裸下标的基名过滤：单字符可以，多字符必须含大写/星号，避免把 pdf_page 这类标识符拆开。"""
    if len(base) == 1:
        return True
    return any(c.isupper() for c in base) or "*" in base or "'" in base


def split_math(text: str):
    """把纯文本切成 [(kind, value, start, end)]，kind 为 text / inline / display。"""
    out, pos = [], 0
    for m in MATH_PAT.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()], pos, m.start()))
        if m.group("display") is not None:
            out.append(("display", m.group("display").strip(), m.start(), m.end()))
        elif m.group("inline") is not None:
            out.append(("inline", m.group("inline").strip(), m.start(), m.end()))
        elif m.group("bdisplay") is not None:
            out.append(("display", m.group("bdisplay").strip(), m.start(), m.end()))
        else:
            out.append(("inline", m.group("binline").strip(), m.start(), m.end()))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:], pos, len(text)))
    return out


def _math_ok(expr: str) -> bool:
    return bool(SAFE_LATEX.match(expr))


def subsup(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    spans = []

    def emit(expr: str) -> str:
        spans.append(expr)
        return f"\x01M{len(spans) - 1}\x01"      # 占位，后续 sub/sup 正则不会改到公式内部

    text = COMBINED.sub(
        lambda m: emit(f"{m.group(1)}^{{{m.group(2)}}}_{{{m.group(3)}}}")
        if _math_ok(f"{m.group(1)}^{{{m.group(2)}}}_{{{m.group(3)}}}") else m.group(0),
        text)
    text = SUB_BRACE.sub(
        lambda m: emit(f"{m.group(1)}_{{{m.group(2)}}}")
        if ("_" in m.group(2) or "^" in m.group(2))
        and _math_ok(f"{m.group(1)}_{{{m.group(2)}}}")
        else f"{m.group(1)}<sub>{m.group(2)}</sub>",
        text)
    text = SUP_BRACE.sub(lambda m: f"{m.group(1)}<sup>{m.group(2)}</sup>", text)
    text = SUB_BARE.sub(
        lambda m: f"{m.group(1)}<sub>{m.group(2)}</sub>"
        if _base_ok(m.group(1)) else m.group(0), text)
    text = SUP_BARE.sub(lambda m: f"{m.group(1)}<sup>{m.group(2)}</sup>", text)
    if spans:
        text = re.sub(r"\x01M(\d+)\x01",
                      lambda m: math_html("inline", spans[int(m.group(1))]), text)
    return text


def math_html(kind: str, latex: str) -> str:
    latex = latex.replace("\n", " ").strip()
    latex = html_lib.escape(latex, quote=False)   # < > & 会被 HTML 解析吃掉，先转义；$ 保留给 Zotero 解析
    if kind == "display":
        return f'<pre class="math">$${latex}$$</pre>'
    return f'<span class="math">${latex}$</span>'


def render_text(text: str, subsup_on: bool, dim_sources: bool, allow_math: bool = True) -> str:
    """纯文本（可能是 HTML 文本节点）-> 带 math/sub/sup 的 HTML 片段。"""
    pieces = []
    for kind, value, start, end in split_math(text):
        if kind == "text" or not allow_math:
            piece = subsup(value if kind == "text" else text[start:end], subsup_on)
            if dim_sources and kind == "text":
                piece = SOURCE_TAG.sub(
                    lambda m: f'<span style="color:#8a8f98">{m.group(0)}</span>', piece)
            pieces.append(piece)
            continue
        # 句中夹着的 $$...$$ 降级为行内，避免把段落/列表项劈成两半
        if kind == "display" and (text[:start].strip() or text[end:].strip()):
            kind = "inline"
        pieces.append(math_html(kind, value))
    return "".join(pieces)


# ---------------------------------------------------------------- Markdown 保护

PLACEHOLDER = "@@ZOTMATH{}@@"
DISPLAY_LINE = re.compile(r"^@@ZOTMATH(\d+)@@$")


def protect_inline(md_text: str):
    """保护 inline code 与数学片段，避免 markdown 把 _ * ^ 当成强调/列表符号。"""
    store = []
    chunks = md_text.split("```")
    for i in range(0, len(chunks), 2):           # 偶数段 = 非代码块
        seg = chunks[i]
        out, pos = [], 0
        for m in re.finditer(r"`[^`\n]*`", seg):
            out.append(_protect_segment(seg[pos:m.start()], store))
            out.append(m.group(0))               # 行内代码原样保留
            pos = m.end()
        out.append(_protect_segment(seg[pos:], store))
        chunks[i] = "".join(out)
    return "```".join(chunks), store


WORD_BEFORE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789}]{)")
WORD_AFTER = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789{[(")


def escape_stars(seg: str) -> str:
    """保护 A*、D*_q、c^{img}*set 这类「星号当符号用」的写法，避免被 markdown 当强调。"""
    def repl(m):
        prev = seg[m.start() - 1] if m.start() else ""
        nxt = seg[m.end()] if m.end() < len(seg) else ""
        if prev in WORD_BEFORE or nxt in WORD_AFTER:
            return r"\*"
        return "*"

    return re.sub(r"\*", repl, seg)


def _protect_segment(seg: str, store: list) -> str:
    out, pos = [], 0
    for m in MATH_PAT.finditer(seg):
        if m.start() > pos:
            out.append(escape_stars(seg[pos:m.start()]))
        store.append((("display", m.group("display").strip()) if m.group("display") is not None
                      else ("inline", m.group("inline").strip()) if m.group("inline") is not None
                      else ("display", m.group("bdisplay").strip()) if m.group("bdisplay") is not None
                      else ("inline", m.group("binline").strip())))
        out.append(PLACEHOLDER.format(len(store) - 1))
        pos = m.end()
    out.append(escape_stars(seg[pos:]))
    return "".join(out)


def restore(html_text: str, store: list) -> str:
    def repl(m):
        kind, latex = store[int(m.group(1))]
        return math_html(kind, latex)

    # 独占一段的行间公式：<p>@@ZOTMATHn@@</p> -> 裸 <pre class="math">
    html_text = re.sub(r"<p>\s*@@ZOTMATH(\d+)@@\s*</p>", repl, html_text)

    def repl_inline(m):
        kind, latex = store[int(m.group(1))]
        return math_html("inline" if kind == "display" else kind, latex)

    return re.sub(r"@@ZOTMATH(\d+)@@", repl_inline, html_text)


# ---------------------------------------------------------------- HTML 后处理

SKIP_TAGS = {"code", "pre", "a", "script", "style", "textarea"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def postprocess_html(html_text: str, subsup_on=True, dim_sources=True) -> str:
    """对已有 note HTML 的文本节点做渲染，跳过 code/pre/a 与已存在的公式节点。"""
    tokens = re.split(r"(<[^>]+>)", html_text)
    out, skip_depth, math_depth, heading_depth = [], 0, 0, 0
    for tok in tokens:
        if tok.startswith("<"):
            low = tok.lower()
            if low.startswith("</"):
                name = re.match(r"</\s*([a-z0-9]+)", low)
                tag = name.group(1) if name else ""
                if tag in SKIP_TAGS and skip_depth:
                    skip_depth -= 1
                elif tag == "span" and math_depth:
                    math_depth -= 1
                elif tag in HEADING_TAGS and heading_depth:
                    heading_depth -= 1
            elif not low.endswith("/>"):
                name = re.match(r"<\s*([a-z0-9]+)", low)
                tag = name.group(1) if name else ""
                if tag in SKIP_TAGS:
                    skip_depth += 1
                elif tag == "span" and 'class="math"' in low:
                    math_depth += 1
                elif tag in HEADING_TAGS:
                    heading_depth += 1
            out.append(tok)
            continue
        if skip_depth or math_depth or not tok.strip():
            out.append(tok)
            continue
        # 标题里 Zotero 不允许 math_inline 节点，保持纯文本 + 上下标
        out.append(render_text(tok, subsup_on, dim_sources, allow_math=not heading_depth))
    return "".join(out)


# ---------------------------------------------------------------- 主流程

def first_h1(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Paper Card"


def md_to_html(md_text: str, subsup_on: bool, dim_sources: bool) -> str:
    protected, store = protect_inline(md_text)
    html_text = markdown.markdown(protected, extensions=["tables", "sane_lists", "nl2br"])
    # 先在占位符状态下处理文本节点，再把占位符换成真正的公式节点，避免二次包裹
    html_text = postprocess_html(html_text, subsup_on, dim_sources)
    return restore(html_text, store)


def main() -> int:
    ap = argparse.ArgumentParser(description="Paper Card Markdown/JSON -> Zotero 笔记 HTML（含公式渲染）")
    ap.add_argument("--card", help="Paper Card 的 .md 路径")
    ap.add_argument("--key", help="Zotero 父条目 key")
    ap.add_argument("--out", help="输出 JSON 路径")
    ap.add_argument("--title", default=None)
    ap.add_argument("--tags", default="paper-card")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--notes", help="存量模式：已有的 zotero_notes.json，就地修复 html")
    ap.add_argument("--no-subsup", action="store_true", help="不转换裸上下标")
    ap.add_argument("--keep-sources", action="store_true", help="不把 [Paper: ...] 变灰")
    args = ap.parse_args()

    subsup_on = not args.no_subsup
    dim_sources = not args.keep_sources

    if args.notes:
        src = Path(args.notes)
        notes = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(notes, list):
            raise SystemExit("notes JSON 顶层不是数组")
        before = sum(n.get("html", "").count('<span class="math">') for n in notes)
        for n in notes:
            if isinstance(n.get("html"), str):
                n["html"] = postprocess_html(n["html"], subsup_on, dim_sources)
        after = sum(n.get("html", "").count('<span class="math">') for n in notes)
        out_path = Path(args.out) if args.out else src
        out_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"fixed {out_path} | notes={len(notes)} 行内公式 {before} -> {after}")
        return 0

    if not (args.card and args.key and args.out):
        raise SystemExit("生成模式需要 --card --key --out（或用 --notes 走存量修复）")

    md_text = Path(args.card).read_text(encoding="utf-8")
    html_text = md_to_html(md_text, subsup_on, dim_sources)

    item = {
        "key": args.key,
        "title": args.title or first_h1(md_text),
        "html": html_text,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()] or ["paper-card"],
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

    h2 = len(re.findall(r"<h2>", html_text))
    tables = html_text.count("<table>")
    inline_math = html_text.count('<span class="math">')
    display_math = html_text.count('<pre class="math">')
    subs = html_text.count("<sub>")
    sups = html_text.count("<sup>")
    residual = len(re.findall(r"\$", html_text)) - (2 * inline_math + 4 * display_math)
    print(f"wrote {out_path} | key={args.key} md_chars={len(md_text)} html_chars={len(html_text)} "
          f"h2={h2} tables={tables} math_inline={inline_math} math_display={display_math} "
          f"sub={subs} sup={sups} residual_$={residual} notes_in_file={len(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
