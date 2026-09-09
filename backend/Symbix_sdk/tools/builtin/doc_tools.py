"""办公文档读写工具(docx/xlsx/pptx/pdf):以 Markdown 为读写媒介。

职责边界(与 file_tools 的 read_file/edit_file 区分):
  - read_file / edit_file   : 只处理纯文本(md/txt/代码/配置)
  - parse_file              : 各种格式 -> 文本给模型(内部已接 markitdown)
  - 本模块(doc_tools)       : 二进制办公文档的“读成 Markdown / 由 Markdown 写成”

写入策略(样式让位、内容优先):
  - md -> docx : markdown-it-py 解析 + python-docx 构建(不依赖 pandoc)
  - md -> xlsx : 解析 md 表格,openpyxl 写入
  - md -> pptx : markdown-it-py 解析 + python-pptx 构建
  - md -> pdf  : fpdf2 纯文本排版(标题放大/段落/代码块),不依赖 LaTeX

依赖缺失时返回明确安装提示,不抛异常。
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from Symbix_sdk.tools.file_pipeline import (
    check_path_in_sandbox,
    get_project_root,
    parse_file_path,
)

# 允许本模块读/写的办公扩展名
DOC_EXTS = {".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt"}


def _resolve(path: str) -> tuple[bool, str]:
    """沙箱校验 + 绝对化。返回 (ok, abs_path_or_error_msg)。"""
    ok, resolved = check_path_in_sandbox(path)
    if not ok:
        return False, resolved  # resolved 是错误信息
    return True, resolved


def _missing_hint(pkg: str, extra: str = "") -> str:
    return f"[缺少依赖] 该操作需要安装 {pkg}。{extra}安装后重启后端即可生效。"


# ---------------------------------------------------------------------------
# Markdown 解析辅助(markdown-it-py)
# ---------------------------------------------------------------------------

def _mdit() -> Any:
    """构建 markdown-it 实例(启用表格)。失败返回 None。"""
    try:
        from markdown_it import MarkdownIt
        return MarkdownIt("commonmark").enable("table")
    except Exception:
        return None


def _md_inline_spans(text: str) -> list[dict]:
    """md 行内文本 → 富文本段 [{text, bold, italic, code}]。"""
    try:
        md = _mdit()
        if md is None:
            raise RuntimeError
        tokens = md.parseInline(text or "", {})
        children = tokens[0].children if tokens else []
    except Exception:
        return [{"text": text or "", "bold": False, "italic": False, "code": False}]
    spans: list[dict] = []
    strong = em = 0
    try:
        for ch in children:
            t = ch.type
            if t == "strong_open":
                strong += 1
            elif t == "strong_close":
                strong = max(0, strong - 1)
            elif t == "em_open":
                em += 1
            elif t == "em_close":
                em = max(0, em - 1)
            elif t == "code_inline":
                spans.append({"text": ch.content, "bold": strong > 0, "italic": em > 0, "code": True})
            elif t == "text":
                spans.append({"text": ch.content, "bold": strong > 0, "italic": em > 0, "code": False})
            elif t in ("softbreak", "hardbreak"):
                spans.append({"text": "\n", "bold": strong > 0, "italic": em > 0, "code": False})
            elif t == "image":
                spans.append({"text": ch.content or "(图片)", "bold": False, "italic": False, "code": False})
    except Exception:
        pass
    if not spans:
        spans = [{"text": text or "", "bold": False, "italic": False, "code": False}]
    return spans


def _md_inline_plain(text: str) -> str:
    """行内富文本 → 纯文本。"""
    return "".join(s["text"] for s in _md_inline_spans(text)).strip()



# ---------------------------------------------------------------------------
# 读:文档 -> Markdown 文本 / Markdown 文件
# ---------------------------------------------------------------------------

def _md_from_xlsx_native(path: str) -> Optional[str]:
    """openpyxl 直读 xlsx 为 md 表格(不依赖 markitdown[xlsx] extra)。"""
    try:
        from openpyxl import load_workbook
    except Exception:
        return None
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                vals = ["" if v is None else str(v).replace("\n", " ") for v in row]
                if any(vals):
                    rows.append(vals)
            if not rows:
                continue
            parts.append(f"## Sheet: {ws.title}")
            # 首行做表头,其余做数据(仅当有多行时用 md 表格)
            parts.append("| " + " | ".join(rows[0]) + " |")
            parts.append("|" + "|".join("---" for _ in rows[0]) + "|")
            for r in rows[1:]:
                # 列数不足补齐
                r = r + [""] * (len(rows[0]) - len(r)) if len(r) < len(rows[0]) else r[: len(rows[0])]
                parts.append("| " + " | ".join(r) + " |")
        wb.close()
        text = "\n".join(parts).strip()
        return text or None
    except Exception:
        return None


def _md_from_pdf_native(path: str, max_chars: int) -> Optional[str]:
    """pypdf 直读 pdf 为纯文本(不依赖 markitdown pdf extra)。"""
    try:
        from pypdf import PdfReader
    except Exception:
        return None
    try:
        reader = PdfReader(path)
        parts = []
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                parts.append(f"--- page {i + 1} ---\n{t}")
            if sum(len(p) for p in parts) > max_chars:
                break
        text = "\n\n".join(parts).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [内容截断 {max_chars} chars]"
        return text or None
    except Exception:
        return None


def _md_from_any(path: str, max_chars: int = 50_000) -> Optional[str]:
    """内部:把办公文档转 Markdown 文本,失败返回 None。"""
    try:
        from markitdown import MarkItDown
    except Exception:
        return None
    try:
        md = MarkItDown()
        try:
            result = md.convert(path)
        except Exception:
            result = md.convert_stream(open(path, "rb"))
        text = (result.text_content or "").strip()
        if not text:
            return None
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [内容截断 {max_chars} chars]"
        return text
    except Exception:
        return None


def doc_to_markdown(file_path: str, max_chars: int = 50_000) -> dict:
    """把办公文档(docx/xlsx/pptx/pdf/doc)解析为 Markdown 文本返回。

    内部优先用 markitdown(微软),失败回退 parse_file_path 的原生解析。
    返回 {"success", "text", "path", "filename", "note"}。
    """
    ok, resolved = _resolve(file_path)
    if not ok:
        return {"success": False, "error": resolved, "text": ""}
    if not os.path.isfile(resolved):
        return {"success": False, "error": f"文件不存在: {resolved}", "text": ""}

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in DOC_EXTS:
        return {
            "success": False,
            "error": f"doc_to_markdown 仅用于办公文档({sorted(DOC_EXTS)}),收到 {ext or '(无扩展名)'}。纯文本文件请用 read_file/parse_file。",
            "text": "",
        }

    # 1) markitdown 全格式
    md_text = _md_from_any(resolved, max_chars)
    if md_text:
        return {
            "success": True,
            "text": md_text,
            "path": resolved,
            "filename": os.path.basename(resolved),
            "note": "via markitdown",
        }

    # 1.5) 扩展名特化原生回退(markitdown 缺 extra 时仍能读)
    if ext == ".xlsx":
        md_text = _md_from_xlsx_native(resolved)
        if md_text:
            return {"success": True, "text": md_text, "path": resolved,
                    "filename": os.path.basename(resolved), "note": "via openpyxl"}
    elif ext == ".pdf":
        md_text = _md_from_pdf_native(resolved, max_chars)
        if md_text:
            return {"success": True, "text": md_text, "path": resolved,
                    "filename": os.path.basename(resolved), "note": "via pypdf"}

    # 2) 回退原生解析(parse_file_path 对 docx/pdf 有内置解析;xlsx/pptx 无则明确提示)
    try:
        parsed = parse_file_path(resolved, include_image_base64=False)
    except Exception as e:
        return {"success": False, "error": f"解析失败: {e}", "text": ""}
    body = (parsed.get("text") or "").strip()
    if parsed.get("status") == "ok" and body and not body.startswith("["):
        return {
            "success": True,
            "text": body,
            "path": resolved,
            "filename": os.path.basename(resolved),
            "note": "via native fallback",
        }
    # 原生也无结果 / 只有提示
    return {
        "success": False,
        "error": body or f"无法解析 {os.path.basename(resolved)}(可能需要安装 markitdown)",
        "text": "",
    }


def doc_to_markdown_file(file_path: str, out_md_path: str) -> dict:
    """把办公文档转成 .md 文件落盘(便于随后 edit_file 编辑 md 再写回)。"""
    r = doc_to_markdown(file_path)
    if not r["success"]:
        return r
    # out 落盘校验(在沙箱内才能写)
    ok, out_abs = _resolve(out_md_path)
    if not ok:
        return {"success": False, "error": out_abs}
    if not out_abs.lower().endswith(".md"):
        return {"success": False, "error": "out_md_path 必须以 .md 结尾"}
    try:
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        with open(out_abs, "w", encoding="utf-8") as f:
            f.write(r["text"])
        return {
            "success": True,
            "md_path": out_abs,
            "text": f"已写入 Markdown: {out_abs}",
        }
    except Exception as e:
        return {"success": False, "error": f"写入失败: {e}"}


# ---------------------------------------------------------------------------
# 写:Markdown -> docx/xlsx/pptx/pdf
# ---------------------------------------------------------------------------

def _split_md_blocks(md: str) -> list[dict]:
    """极简 md 块切分:返回 [{'type': heading/code/table/para/list, ...}]。

    只服务没有 pandoc 时的回退渲染;够用但不追求完整 md 规范。
    """
    blocks: list[dict] = []
    lines = (md or "").splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        # 代码块
        if line.lstrip().startswith("```"):
            lang = line.lstrip()[3:].strip()
            buf = []
            i += 1
            while i < n and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束 ```
            blocks.append({"type": "code", "lang": lang, "text": "\n".join(buf)})
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue
        # 表格(以 | 开头且下一行是分隔行)
        if line.startswith("|") and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue
        # 列表:连续收集
        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < n and (re.match(r"^\s*[-*+]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])):
                items.append(re.sub(r"^\s*[-*+]\s+|^\s*\d+\.\s+", "", lines[i].rstrip()))
                i += 1
            blocks.append({"type": "list", "items": items})
            continue
        # 段落(合并连续文本行)
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not lines[i].lstrip().startswith(("```", "#")) and not lines[i].strip().startswith("|") and not re.match(r"^\s*[-*+]\s+", lines[i]) and not re.match(r"^\s*\d+\.\s+", lines[i]):
            para.append(lines[i].rstrip())
            i += 1
        blocks.append({"type": "para", "text": "\n".join(para).strip()})
    return blocks


def _strip_inline_md(text: str) -> str:
    """去掉常见行内 md 标记,保留可见文本。"""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 图片 ![alt](url)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # 链接 [text](url)
    text = re.sub(r"`([^`]*)`", r"\1", text)               # 行内代码
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)         # 粗体
    text = re.sub(r"\*([^*]+)\*", r"\1", text)             # 斜体
    text = re.sub(r"~~([^~]+)~~", r"\1", text)             # 删除线
    return text.strip()


def md_to_docx(md_content: str, out_path: str) -> dict:
    """把 Markdown 文本写成 .docx 文件(markdown-it-py 解析 + python-docx 构建)。

    支持标题/段落/粗斜体/有序无序列表/表格/代码块/引用。
    样式让位、内容优先,不依赖 pandoc。
    """
    ok, out_abs = _resolve(out_path)
    if not ok:
        return {"success": False, "error": out_abs}
    if not out_abs.lower().endswith(".docx"):
        return {"success": False, "error": "out_path 必须以 .docx 结尾"}
    try:
        from docx import Document
    except ImportError:
        return {"success": False, "error": _missing_hint("python-docx", "pip install python-docx")}
    try:
        doc = Document()
        _render_docx_tokens(doc, md_content or "")
        doc.save(out_abs)
        return {"success": True, "path": out_abs, "note": "via markdown-it + python-docx"}
    except Exception as e:
        return {"success": False, "error": f"python-docx 写入失败: {e}"}


def _render_docx_tokens(doc, md_content: str) -> None:
    """markdown-it token 流 → docx(就地追加)。markdown-it 缺失时降级粗渲染。"""
    md = _mdit()
    if md is None:
        for blk in _split_md_blocks(md_content or ""):
            _docx_apply_block(doc, blk)
        return
    try:
        _docx_render_tokens(doc, md.parse(md_content or ""))
    except Exception:
        for blk in _split_md_blocks(md_content or ""):
            _docx_apply_block(doc, blk)


def _docx_set_run(run, bold=None, italic=None, code=False):
    """设置 run 中文字体(微软雅黑 eastAsia)+ 粗/斜/代码字体。"""
    try:
        from docx.oxml.ns import qn
        run.font.name = "Consolas" if code else "Microsoft YaHei"
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        if bold is not None:
            run.font.bold = bold
        if italic is not None:
            run.font.italic = italic
    except Exception:
        pass


def _docx_add_rich(p, text: str):
    """把 md 行内文本按富文本段添加到 paragraph(粗/斜/代码)。"""
    for sp in _md_inline_spans(text):
        r = p.add_run(sp["text"])
        _docx_set_run(r, bold=sp["bold"], italic=sp["italic"], code=sp["code"])


def _docx_apply_block(doc, blk):
    """降级路径:_split_md_blocks 的块渲染进 docx。"""
    if blk["type"] == "heading":
        h = doc.add_heading(level=min(blk["level"], 6))
        _docx_add_rich(h, blk["text"])
    elif blk["type"] == "para":
        _docx_add_rich(doc.add_paragraph(), blk["text"])
    elif blk["type"] == "list":
        for it in blk["items"]:
            _docx_add_rich(doc.add_paragraph(style="List Bullet"), it)
    elif blk["type"] == "code":
        p = doc.add_paragraph()
        r = p.add_run(blk["text"])
        _docx_set_run(r, code=True)
    elif blk["type"] == "table":
        ncols = max(1, len(blk["header"]))
        table = doc.add_table(rows=1 + len(blk["rows"]), cols=ncols)
        try:
            table.style = "Light Grid Accent 1"
        except Exception:
            pass
        for j, c in enumerate(blk["header"]):
            table.cell(0, j).text = _strip_inline_md(c)
        for ri, row in enumerate(blk["rows"]):
            for j in range(ncols):
                table.cell(ri + 1, j).text = _strip_inline_md(row[j]) if j < len(row) else ""


def _docx_render_tokens(doc, tokens) -> None:
    """markdown-it token 序列 → docx。假定 markdown-it 已启用 table。"""
    from docx.oxml.ns import qn  # noqa: F401 (引用于 _docx_set_run)

    def _inline_text(tk) -> str:
        """返回行内 token 的原始 md 源(含 ** * ` 等标记,供 _docx_add_rich 解析)。"""
        return tk.content or ""

    def _add_rich(p, text: str):
        _docx_add_rich(p, text)

    def _add_table(header, rows):
        ncols = max(1, len(header))
        table = doc.add_table(rows=1 + len(rows), cols=ncols)
        try:
            table.style = "Light Grid Accent 1"
        except Exception:
            pass
        for j, c in enumerate(header):
            table.cell(0, j).text = _strip_inline_md(c)
        for ri, row in enumerate(rows):
            for j in range(ncols):
                table.cell(ri + 1, j).text = _strip_inline_md(row[j]) if j < len(row) else ""

    i, n = 0, len(tokens)
    guard = 0
    while i < n:
        guard += 1
        if guard > 20000:
            break
        t = tokens[i]
        if t.type == "heading_open":
            lvl = min(int(t.tag[1]) if t.tag and t.tag[0] == "h" else 1, 6)
            i += 1
            text = ""
            while i < n and tokens[i].type != "heading_close":
                if tokens[i].type == "inline":
                    text = _inline_text(tokens[i])
                i += 1
            h = doc.add_heading(level=lvl)
            _docx_add_rich(h, text)
        elif t.type == "paragraph_open":
            i += 1
            text = ""
            while i < n and tokens[i].type != "paragraph_close":
                if tokens[i].type == "inline":
                    text = _inline_text(tokens[i])
                i += 1
            p = doc.add_paragraph()
            _docx_add_rich(p, text)
        elif t.type == "bullet_list_open":
            i += 1
            while i < n and tokens[i].type != "bullet_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    parts = []
                    while i < n and tokens[i].type != "list_item_close":
                        if tokens[i].type == "inline":
                            parts.append(_inline_text(tokens[i]))
                        i += 1
                    p = doc.add_paragraph(style="List Bullet")
                    _docx_add_rich(p, "".join(parts))
                else:
                    i += 1
        elif t.type == "ordered_list_open":
            i += 1
            while i < n and tokens[i].type != "ordered_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    parts = []
                    while i < n and tokens[i].type != "list_item_close":
                        if tokens[i].type == "inline":
                            parts.append(_inline_text(tokens[i]))
                        i += 1
                    p = doc.add_paragraph(style="List Number")
                    _docx_add_rich(p, "".join(parts))
                else:
                    i += 1
        elif t.type == "fence":
            p = doc.add_paragraph()
            r = p.add_run(t.content)
            _docx_set_run(r, code=True)
            i += 1
        elif t.type == "table_open":
            i += 1
            header = []
            rows = []
            cur = []
            in_head = False
            while i < n and tokens[i].type != "table_close":
                tt = tokens[i].type
                if tt in ("thead_open", "tbody_open"):
                    in_head = tt == "thead_open"
                    i += 1
                    continue
                if tt == "tr_open":
                    cur = []
                    i += 1
                    continue
                if tt == "tr_close":
                    if cur:
                        if in_head:
                            header = cur
                        else:
                            rows.append(cur)
                    i += 1
                    continue
                if tt in ("th_open", "td_open"):
                    i += 1
                    cell = ""
                    while i < n and tokens[i].type not in ("th_close", "td_close"):
                        if tokens[i].type == "inline":
                            cell = _inline_text(tokens[i])
                        i += 1
                    cur.append(cell)
                else:
                    i += 1
            _add_table(header, rows)
        elif t.type == "blockquote_open":
            i += 1
            parts = []
            while i < n and tokens[i].type != "blockquote_close":
                if tokens[i].type == "inline":
                    parts.append(_inline_text(tokens[i]))
                i += 1
            p = doc.add_paragraph(style="Intense Quote")
            _docx_add_rich(p, "".join(parts))
        else:
            i += 1


def _parse_md_tables(md_content: str) -> list[dict]:
    """从 md 提取所有表格:[{'header': [...], 'rows': [[...]]}]。"""
    tables = []
    lines = (md_content or "").splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().startswith("|") and i + 1 < n and "-" in lines[i + 1] and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            tables.append({"header": header, "rows": rows})
            continue
        i += 1
    return tables


def md_to_xlsx(md_content: str, out_path: str) -> dict:
    """把 Markdown 中的表格写成 .xlsx(每个 md 表格一个 sheet;无表格时整段作一列)。"""
    ok, out_abs = _resolve(out_path)
    if not ok:
        return {"success": False, "error": out_abs}
    if not out_abs.lower().endswith((".xlsx", ".xls")):
        return {"success": False, "error": "out_path 必须以 .xlsx 结尾"}
    try:
        from openpyxl import Workbook
    except ImportError:
        return {"success": False, "error": _missing_hint("openpyxl", "pip install openpyxl")}

    try:
        tables = _parse_md_tables(md_content)
        wb = Workbook()
        ws0 = wb.active
        if not tables:
            ws0.title = "Sheet1"
            ws0.cell(row=1, column=1, value=_strip_inline_md(md_content).strip()[:32767])
        else:
            # 首个表格用默认 sheet,其余追加
            for ti, t in enumerate(tables, start=1):
                ws = ws0 if ti == 1 else wb.create_sheet(title=f"Sheet{ti}")
                for j, cell in enumerate(t["header"], start=1):
                    ws.cell(row=1, column=j, value=_strip_inline_md(cell))
                for ri, row in enumerate(t["rows"], start=2):
                    for j in range(1, max(2, len(t["header"]) + 1)):
                        val = row[j - 1] if j - 1 < len(row) else ""
                        ws.cell(row=ri, column=j, value=_strip_inline_md(val))
        wb.save(out_abs)
        return {"success": True, "path": out_abs, "note": f"{len(tables)} 个表格" if tables else "文本单列"}
    except Exception as e:
        return {"success": False, "error": f"openpyxl 写入失败: {e}"}


def md_to_pptx(md_content: str, out_path: str) -> dict:
    """把 Markdown 写成 .pptx(按 ## / ### 分页,正文做要点)。"""
    ok, out_abs = _resolve(out_path)
    if not ok:
        return {"success": False, "error": out_abs}
    if not out_abs.lower().endswith(".pptx"):
        return {"success": False, "error": "out_path 必须以 .pptx 结尾"}
    try:
        from pptx import Presentation
        from pptx.util import Pt
    except ImportError:
        return {"success": False, "error": _missing_hint("python-pptx", "pip install python-pptx")}

    try:
        prs = Presentation()
        # 按标题切分页:### 级别开新页
        slides_blocks: list[dict] = []
        cur = None
        for blk in _split_md_blocks(md_content):
            if blk["type"] == "heading" and blk["level"] <= 2:
                cur = {"title": _strip_inline_md(blk["text"]), "body": []}
                slides_blocks.append(cur)
            elif cur is None:
                cur = {"title": "内容", "body": []}
                slides_blocks.append(cur)
                cur["body"].append(blk)
            else:
                cur["body"].append(blk)
        if not slides_blocks:
            slides_blocks = [{"title": "内容", "body": []}]
        for sb in slides_blocks:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            title = slide.shapes.title
            if title is not None:
                title.text = sb["title"][:120]
            body = slide.placeholders[1] if len(slide.placeholders) > 1 else None
            if body is None:
                continue
            tf = body.text_frame
            tf.clear()
            first = True
            for blk in sb["body"]:
                if blk["type"] in ("para", "code"):
                    lines = (blk.get("text") or "").splitlines()
                elif blk["type"] == "list":
                    lines = [f"• {it}" for it in blk["items"]]
                else:
                    lines = []
                for ln in lines:
                    p = tf.paragraphs[0] if first else tf.add_paragraph()
                    first = False
                    p.text = _strip_inline_md(ln)[:200]
                    p.level = 0
        prs.save(out_abs)
        return {"success": True, "path": out_abs, "note": f"{len(slides_blocks)} 页"}
    except Exception as e:
        return {"success": False, "error": f"python-pptx 写入失败: {e}"}


def md_to_pdf(md_content: str, out_path: str) -> dict:
    """把 Markdown 写成 .pdf(fpdf2 纯文本排版,不依赖 LaTeX)。"""
    ok, out_abs = _resolve(out_path)
    if not ok:
        return {"success": False, "error": out_abs}
    if not out_abs.lower().endswith(".pdf"):
        return {"success": False, "error": "out_path 必须以 .pdf 结尾"}
    try:
        from fpdf import FPDF
    except ImportError:
        return {"success": False, "error": _missing_hint("fpdf2", "pip install fpdf2")}

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        # 中文字体:只注册单一常规变体。fpdf2 对 CJK 字体存在两个坑:
        #  1) 同页切换粗/常 TTF 变体后渲染中文报 Not enough horizontal space
        #  2) 连续多次短内容 multi_cell 同样报错(第二次起)
        # 规避:标题仅用放大字号;正文统一用 write()(内部自行分页/折行,无此 bug)。
        font_path = None
        for cand in (
            r"C:\Windows\Fonts\Deng.ttf",       # 等线
            r"C:\Windows\Fonts\STSONG.TTF",    # 宋体
            r"C:\Windows\Fonts\SIMLI.TTF",
            r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
        ):
            if os.path.isfile(cand):
                font_path = cand
                break
        if font_path:
            pdf.add_font("zh", "", font_path)

        def _write(text: str, size: int, h: float = 7):
            if font_path:
                pdf.set_font("zh", "", size=size)
            else:
                pdf.set_font("Helvetica", "", size=size)
            # write 每字符累积宽度;以行高 h 渲染。自动处理分页。
            pdf.write(h, text)
            pdf.ln(h * 1.05)

        for blk in _split_md_blocks(md_content):
            if blk["type"] == "heading":
                _write(_strip_inline_md(blk["text"]), max(14, 20 - blk["level"] * 2), h=9)
                pdf.ln(1)
            elif blk["type"] == "para":
                _write(_strip_inline_md(blk["text"]), 11)
            elif blk["type"] == "code":
                _write(blk.get("text") or "", 10)
            elif blk["type"] == "list":
                for it in blk["items"]:
                    _write(f"• {_strip_inline_md(it)}", 11)
        pdf.output(out_abs)
        note = "" if font_path else "(未找到中文字体,中文可能显示为方块;可安装中文字体)"
        return {"success": True, "path": out_abs, "note": note}
    except Exception as e:
        return {"success": False, "error": f"fpdf2 写入失败: {e}"}


# ---------------------------------------------------------------------------
# 工具 schema 注册表 (供 tool_setup.py 统一注册)
# ---------------------------------------------------------------------------

DOC_TOOLS_SCHEMAS = {
    "doc_to_markdown": {
        "risk_channel": "read",
        "func": doc_to_markdown,
        "description": (
            "读取办公文档(docx/xlsx/pptx/pdf/doc)并把内容解析为 Markdown 文本返回,"
            "供模型分析/理解。适用于论文、合同、报告、表格等二进制文档 —— read_file/parse_file 读不了或读不全时用它。"
            "内部优先用 markitdown,自动降级。返回文本可能较长,注意 max_chars。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "办公文档的绝对路径或工作区内路径",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "返回文本最大字符数,默认 50000",
                    "default": 50000,
                },
            },
            "required": ["file_path"],
        },
    },
    "doc_to_markdown_file": {
        "risk_channel": "write",
        "func": doc_to_markdown_file,
        "description": (
            "把办公文档(docx/xlsx/pptx/pdf)转换成 .md 文件保存到指定路径。"
            "适合先转 md 便于反复编辑,再用 md_to_docx/md_to_xlsx 等写回。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "源办公文档路径",
                },
                "out_md_path": {
                    "type": "string",
                    "description": "输出的 .md 文件路径(必须以 .md 结尾)",
                },
            },
            "required": ["file_path", "out_md_path"],
        },
    },
    "md_to_docx": {
        "risk_channel": "write",
        "func": md_to_docx,
        "description": (
            "把 Markdown 内容写成 .docx 文件(新建或覆盖)。"
            "适合把模型整理的文本/报告落成 Word。样式以默认模板为主(内容优先、样式让位)。"
            "注意:这不是对已有 docx 的原地编辑 —— 若想修改已有 docx,先用 doc_to_markdown 读出内容,"
            "修改后调用本工具写到一个新 .docx 路径(原样式不会保留)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "md_content": {
                    "type": "string",
                    "description": "要写入的 Markdown 文本",
                },
                "out_path": {
                    "type": "string",
                    "description": "输出的 .docx 路径",
                },
            },
            "required": ["md_content", "out_path"],
        },
    },
    "md_to_xlsx": {
        "risk_channel": "write",
        "func": md_to_xlsx,
        "description": (
            "把 Markdown 中的表格写成 .xlsx(每个 md 表格一个 sheet;没有表格时整段放第一列)。"
            "用于生成/更新 Excel 数据文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "md_content": {
                    "type": "string",
                    "description": "含 Markdown 表格的文本,如 '| 列1 | 列2 |\\n| --- | --- |\\n| a | b |'",
                },
                "out_path": {
                    "type": "string",
                    "description": "输出的 .xlsx 路径",
                },
            },
            "required": ["md_content", "out_path"],
        },
    },
    "md_to_pptx": {
        "risk_channel": "write",
        "func": md_to_pptx,
        "description": "把 Markdown 写成 .pptx(按二级/三级标题分页,正文与列表做幻灯片要点)。",
        "parameters": {
            "type": "object",
            "properties": {
                "md_content": {
                    "type": "string",
                    "description": "Markdown 文本,建议用 ## / ### 分节作为每页标题",
                },
                "out_path": {
                    "type": "string",
                    "description": "输出的 .pptx 路径",
                },
            },
            "required": ["md_content", "out_path"],
        },
    },
    "md_to_pdf": {
        "risk_channel": "write",
        "func": md_to_pdf,
        "description": (
            "把 Markdown 写成 .pdf(fpdf2 纯文本排版,标题加粗/段落/列表,不依赖 LaTeX)。"
            "适合简单文本型 PDF;复杂排版/图表请先用其他工具生成再转。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "md_content": {
                    "type": "string",
                    "description": "Markdown 文本",
                },
                "out_path": {
                    "type": "string",
                    "description": "输出的 .pdf 路径",
                },
            },
            "required": ["md_content", "out_path"],
        },
    },
}
