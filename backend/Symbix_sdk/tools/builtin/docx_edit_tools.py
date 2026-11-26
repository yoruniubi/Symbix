"""docx 原地读取与编辑（保留原有样式）。

为什么单独一个文件:

``doc_tools.py`` 走的是「读成 Markdown → 重新生成 docx」的路子,样式必然全丢
(工具描述里也明说了)。而用户真正要的是**改而不坏** —— 在一份排版好的合同/
报告上改几处文字或格式,其余原样不动。

这里只做原地编辑:打开已有 ``.docx``,改指定段落/run 的属性,再存回同一个
文件。python-docx 操作的是完整 OOXML,只动被点名的 ``rPr``/``pPr``,
不会像重新生成那样把样式清空。

定位方式统一用**下标**(段落序号 / run 序号),下标由 ``inspect_docx`` 给出。
不用文本匹配:同文异格的段落很多(比如两处「注:」),下标是唯一可靠的坐标。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from docx.oxml.ns import qn

from Symbix_sdk.tools.file_pipeline import check_path_in_sandbox

#: 单次 inspect 最多输出多少个段落/表格,防止超长文档把上下文顶爆
INSPECT_MAX_ITEMS = 400

#: 允许修改的字体属性白名单(值是 python-docx 的属性名)
_RUN_ATTRS = ("bold", "italic", "underline", "strike")

#: 段落对齐的字符串 → WD_ALIGN_PARAGRAPH 的取值映射
_ALIGN_ALIASES = {
    "left": "LEFT", "左": "LEFT", "左对齐": "LEFT",
    "center": "CENTER", "centre": "CENTER", "中": "CENTER", "居中": "CENTER",
    "right": "RIGHT", "右": "RIGHT", "右对齐": "RIGHT",
    "justify": "JUSTIFY", "两端": "JUSTIFY", "两端对齐": "JUSTIFY",
    "distribute": "DISTRIBUTE", "分散": "DISTRIBUTE",
}


def _guard(path: str) -> tuple[bool, str]:
    """沙箱校验 + 绝对化。返回 (ok, abs_path_or_error)。

    所有对外工具的第一行都必须过这里。缺了它,模型就能读写工作区外的任意
    文件 —— 与 doc_tools.py 的 ``_resolve`` 保持同一套规则。
    """
    ok, resolved = check_path_in_sandbox(path)
    if not ok:
        return False, resolved
    return True, resolved


def _open(path: str):
    """打开 docx;失败抛 ValueError(消息可直接回给模型)。"""
    ok, resolved = _guard(path)
    if not ok:
        raise ValueError(resolved)
    path = resolved
    try:
        from docx import Document
    except ImportError as e:
        raise ValueError(
            "[缺少依赖] 该操作需要 python-docx。pip install python-docx 后重启后端即可生效。"
        ) from e
    if not os.path.isfile(path):
        raise ValueError(f"文件不存在: {path}")
    if not path.lower().endswith(".docx"):
        raise ValueError(
            "只支持 .docx。旧版 .doc 需先另存为 .docx(或先用 doc_to_markdown 读内容另存)。"
        )
    return Document(path)


def _shade_fill(el) -> Optional[str]:
    """取某个 XML 元素下 ``w:shd`` 的填充色。"""
    if el is None:
        return None
    pPr = el.find(qn("w:pPr")) if el.tag == qn("w:p") else el
    if pPr is None:
        return None
    shd = pPr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.get(qn("w:fill"))


def _int_to_hex(n: int) -> str:
    return f"{n:06X}"


def _run_style_desc(r) -> list[str]:
    """一个 run 的样式描述片段列表。"""
    bits: list[str] = []
    if r.bold:
        bits.append("粗")
    if r.italic:
        bits.append("斜")
    if r.underline:
        bits.append("下划线")
    if r.font.strike:
        bits.append("删除线")
    if r.font.size:
        bits.append(f"{r.font.size.pt:g}pt")
    if r.font.name:
        bits.append(r.font.name)
    try:
        col = r.font.color
        if col is not None and col.type is not None and col.rgb is not None:
            bits.append(f"#{col.rgb}")
    except Exception:
        pass
    return bits


def _para_meta(p) -> list[str]:
    """一个段落的格式描述片段列表。"""
    meta: list[str] = []
    try:
        if p.style is not None and p.style.name not in ("Normal", "正文"):
            meta.append(p.style.name)
    except Exception:
        pass
    pf = p.paragraph_format
    if pf.alignment is not None:
        meta.append(str(pf.alignment).split()[0].lower())
    if pf.first_line_indent is not None:
        try:
            meta.append(f"首行缩进{pf.first_line_indent.pt:g}pt")
        except Exception:
            pass
    if pf.left_indent is not None:
        try:
            meta.append(f"左缩进{pf.left_indent.pt:g}pt")
        except Exception:
            pass
    if pf.line_spacing is not None:
        meta.append(f"行距{pf.line_spacing}")
    if pf.space_before is not None:
        try:
            meta.append(f"段前{pf.space_before.pt:g}pt")
        except Exception:
            pass
    if pf.space_after is not None:
        try:
            meta.append(f"段后{pf.space_after.pt:g}pt")
        except Exception:
            pass
    fill = _shade_fill(p._p)
    if fill:
        meta.append(f"底纹#{fill}")
    return meta


def _iter_all_paragraphs(doc, with_location: bool = False):
    """遍历文档里**全部**段落:正文 + 表格单元格 + 嵌套表格 + 页眉页脚。

    python-docx 的 ``doc.paragraphs`` 只给正文顶层段落,表格里的一个都拿不到
    —— 只改顶层会漏掉一大半内容。这里按「先顶层、再表格(深度优先)、最后
    页眉页脚」的顺序编号,与 inspect 输出的下标严格一致。

    Args:
        doc: python-docx Document。
        with_location: 为 True 时额外返回一个来源标签(如 ``表格1 行0 列1``),
            仅用于展示;默认只返回 (下标,段落) 二元组。
    """
    idx = 0

    def walk(container, loc: str):
        nonlocal idx
        for p in container.paragraphs:
            yield (idx, p, loc) if with_location else (idx, p)
            idx += 1
        for ti, tbl in enumerate(getattr(container, "tables", []), start=1):
            for ri, row in enumerate(tbl.rows):
                for ci, cell in enumerate(row.cells):
                    yield from walk(cell, f"表格{ti} 行{ri} 列{ci}")

    yield from walk(doc, "正文")
    for si, section in enumerate(doc.sections):
        for kind, part in (("页眉", section.header), ("页脚", section.footer)):
            try:
                yield from walk(part, f"{kind} 节{si}")
            except Exception:
                continue


def inspect_docx(file_path: str, max_items: int = INSPECT_MAX_ITEMS) -> dict:
    """列出 docx 的段落/表格结构及其样式,供模型决定改哪里。

    Args:
        file_path: .docx 路径。
        max_items: 最多输出多少个段落条目(防止长文档刷屏)。

    Returns:
        {"success", "text", "path", "paragraph_count", "truncated"} 或
        {"success": False, "error"}。
    """
    try:
        doc = _open(file_path)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"打开失败: {e}"}

    lines: list[str] = []
    shown = 0
    truncated = False

    for idx, p, loc in _iter_all_paragraphs(doc, with_location=True):
        text = (p.text or "").strip()
        meta = _para_meta(p)
        where = "" if loc == "正文" else f" [{loc}]"
        if not text:
            # 空段落仍占一个下标;只有带格式或不在正文时才值得一行(否则全是噪声)
            if meta or loc != "正文":
                if shown >= max_items:
                    truncated = True
                    break
                lines.append(f"段落[{idx}]{where} (空) ({', '.join(meta)})" if meta
                             else f"段落[{idx}]{where} (空)")
                shown += 1
            continue
        if shown >= max_items:
            truncated = True
            break
        head = f"段落[{idx}]{where}"
        if meta:
            head += f" ({', '.join(meta)})"
        runs = " ".join(
            f"「{r.text}」={'/'.join(_run_style_desc(r)) or '默认'}"
            for r in p.runs
            if (r.text or "").strip()
        )
        lines.append(f"{head} {runs}")
        shown += 1

    # 表格轮廓单独列一行,方便看行列结构(单元格内文字已在上面的段落里出现)
    for ti, tbl in enumerate(doc.tables, start=1):
        lines.append(f"表格[{ti}]: {len(tbl.rows)} 行 x {len(tbl.columns)} 列")
        for ri, row in enumerate(tbl.rows):
            cells = []
            for ci, c in enumerate(row.cells):
                tag = (c.text or "").strip() or "(空)"
                fill = _shade_fill(c._tc)
                if fill:
                    tag += f"(底纹#{fill})"
                cells.append(f"[{ci}]{tag}")
            lines.append(f"  行{ri}: " + " | ".join(cells))

    note = ""
    if truncated:
        note = f"\n\n... 已达输出上限 {max_items} 条,剩余段落未列出。"

    return {
        "success": True,
        "text": "\n".join(lines) + note,
        "path": os.path.abspath(file_path),
        "paragraph_count": sum(1 for _ in _iter_all_paragraphs(doc)),
        "truncated": truncated,
    }


def _find_paragraph(doc, index: int):
    """按下标取段落;越界抛 ValueError。"""
    for i, p in _iter_all_paragraphs(doc):
        if i == index:
            return p
    raise ValueError(
        f"段落下标 {index} 不存在。请先调用 inspect_docx 确认有效下标"
        f"(范围 0 ~ 段落总数-1)。"
    )


def _parse_color(value: str) -> Any:
    """``RRGGBB`` / ``#RRGGBB`` / ``auto`` → RGBColor 或 None(auto)。"""
    from docx.shared import RGBColor

    v = (value or "").strip().lstrip("#")
    if v.lower() in ("auto", "none", "default", "默认"):
        return None
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
        raise ValueError(f"颜色格式不对: {value!r},应为 6 位十六进制如 FF0000")
    return RGBColor.from_string(v.upper())


def _set_shading(p_el, fill: Optional[str]) -> None:
    """给段落写 ``w:shd`` 底纹;fill 为空则删除。"""
    from docx.oxml import OxmlElement

    pPr = p_el.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_el.insert(0, pPr)
    shd = pPr.find(qn("w:shd"))
    if not fill:
        if shd is not None:
            pPr.remove(shd)
        return
    if shd is None:
        shd = OxmlElement("w:shd")
        pPr.append(shd)
    shd.set(qn("w:fill"), fill.lstrip("#").upper())


def format_docx(
    file_path: str,
    paragraph: int,
    run: Optional[int] = None,
    size: Optional[float] = None,
    color: Optional[str] = None,
    font: Optional[str] = None,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strike: Optional[bool] = None,
    align: Optional[str] = None,
    first_line_indent: Optional[float] = None,
    left_indent: Optional[float] = None,
    line_spacing: Optional[float] = None,
    space_before: Optional[float] = None,
    space_after: Optional[float] = None,
    shading: Optional[str] = None,
    out_path: str = "",
) -> dict:
    """原地修改 docx 某一段(或其中某个 run)的格式,其余内容一律不动。

    只改显式传入的参数,没传的一律保持原样 —— 这是「改而不坏」的关键。

    Args:
        file_path: .docx 路径。
        paragraph: 段落下标(由 inspect_docx 给出)。
        run: run 下标;留空表示该段落**全部** run(段落级格式如 align 总是作用于整段)。
        size: 字号(磅)。
        color: 字体颜色,6 位十六进制如 ``FF0000``;``auto`` 表示自动色。
        font: 字体名(如 ``SimHei`` / ``微软雅黑``)。
        bold/italic/underline/strike: 字重/斜体/下划线/删除线,True/False。
        align: 对齐方式 left/center/right/justify/distribute。
        first_line_indent: 首行缩进(磅)。
        left_indent: 左缩进(磅)。
        line_spacing: 行距(倍数,如 1.5)。
        space_before/space_after: 段前/段后间距(磅)。
        shading: 段落底纹色,6 位十六进制;``none`` 表示清除。
        out_path: 另存路径;留空表示覆盖原文件。

    Returns:
        {"success", "path", "changed": [...说明...]} 或 {"success": False, "error"}。
    """
    try:
        doc = _open(file_path)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"打开失败: {e}"}

    try:
        para = _find_paragraph(doc, int(paragraph))
    except (ValueError, TypeError) as e:
        return {"success": False, "error": str(e)}

    changed: list[str] = []

    # ── 段落级格式 ──
    pf = para.paragraph_format
    if align is not None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        key = str(align).strip().lower()
        target = _ALIGN_ALIASES.get(key)
        if target is None:
            return {
                "success": False,
                "error": f"align 不支持 {align!r},可选: left/center/right/justify/distribute",
            }
        pf.alignment = getattr(WD_ALIGN_PARAGRAPH, target)
        changed.append(f"对齐={target.lower()}")

    for attr, value, label in (
        ("first_line_indent", first_line_indent, "首行缩进"),
        ("left_indent", left_indent, "左缩进"),
        ("space_before", space_before, "段前"),
        ("space_after", space_after, "段后"),
    ):
        if value is None:
            continue
        from docx.shared import Pt

        setattr(pf, attr, Pt(float(value)))
        changed.append(f"{label}={float(value):g}pt")

    if line_spacing is not None:
        pf.line_spacing = float(line_spacing)
        changed.append(f"行距={float(line_spacing):g}")

    if shading is not None:
        fill = str(shading).strip().lstrip("#")
        if fill.lower() in ("none", "clear", "无", ""):
            _set_shading(para._p, None)
            changed.append("底纹=清除")
        else:
            if len(fill) not in (3, 6):
                return {"success": False, "error": f"shading 格式不对: {shading!r}"}
            _set_shading(para._p, fill)
            changed.append(f"底纹=#{fill.upper()}")

    # ── run 级格式 ──
    run_attrs_given = any(
        v is not None
        for v in (size, color, font, bold, italic, underline, strike)
    )
    if run_attrs_given:
        if not para.runs:
            return {
                "success": False,
                "error": f"段落[{paragraph}] 没有任何文本 run,无法设置字体属性。"
                f"可能是个空段落,或文字都在超链接/域里(暂不支持)。",
            }

        if run is not None:
            try:
                ri = int(run)
                target_runs = [para.runs[ri]]
            except (ValueError, TypeError, IndexError):
                return {
                    "success": False,
                    "error": f"run 下标 {run} 越界,该段落共 {len(para.runs)} 个 run"
                    f"(有效范围 0 ~ {len(para.runs) - 1})。",
                }
            scope = f"run[{run}]"
        else:
            target_runs = list(para.runs)
            scope = f"全部 {len(target_runs)} 个 run"

        from docx.shared import Pt

        # 颜色先解析好:非法值要在动任何 run 之前就报错,
        # 否则可能已经把前几个 run 改掉一半才抛异常,文件处于半改状态。
        rgb = None
        if color is not None:
            try:
                rgb = _parse_color(color)
            except ValueError as e:
                return {"success": False, "error": str(e)}

        for r in target_runs:
            if size is not None:
                r.font.size = Pt(float(size))
            if rgb is not None or (color is not None and rgb is None):
                r.font.color.rgb = rgb
            if font is not None:
                r.font.name = font
                # 中文字体要额外写 eastAsia,否则 Word 里中文仍用默认字体。
                # rFonts 可能不存在(全新 run 没写过字体时),直接取 .rFonts 会 NoneType 报错。
                rPr = r._element.get_or_add_rPr()
                rFonts = rPr.find(qn("w:rFonts"))
                if rFonts is None:
                    from docx.oxml import OxmlElement

                    rFonts = OxmlElement("w:rFonts")
                    rPr.insert(0, rFonts)
                rFonts.set(qn("w:eastAsia"), font)
            if bold is not None:
                r.bold = bool(bold)
            if italic is not None:
                r.italic = bool(italic)
            if underline is not None:
                r.underline = bool(underline)
            if strike is not None:
                r.font.strike = bool(strike)

        bits = []
        if size is not None:
            bits.append(f"{float(size):g}pt")
        if color is not None:
            bits.append(f"#{str(color).lstrip('#').upper()}")
        if font is not None:
            bits.append(font)
        for name, val in (("粗", bold), ("斜", italic), ("下划线", underline), ("删除线", strike)):
            if val is not None:
                bits.append(name if val else f"取消{name}")
        changed.append(f"{scope}={'/'.join(bits)}")

    if not changed:
        return {
            "success": False,
            "error": "没有传入任何要修改的格式参数,文件未改动。",
        }

    if out_path:
        ok, resolved_out = _guard(out_path)
        if not ok:
            return {"success": False, "error": resolved_out}
        target_path = resolved_out
    else:
        target_path = os.path.abspath(file_path)
    try:
        doc.save(target_path)
    except Exception as e:
        return {"success": False, "error": f"保存失败: {e}"}

    return {"success": True, "path": target_path, "changed": changed}


def replace_docx_text(
    file_path: str,
    replacements: dict,
    whole_document: bool = True,
    paragraph: Optional[int] = None,
    out_path: str = "",
) -> dict:
    """在 docx 里替换文字,**保持原格式**(字体/字号/颜色/加粗等逐字不动)。

    Args:
        file_path: .docx 路径。
        replacements: ``{"旧":"新"}`` 映射。
        whole_document: True=全文档(正文+表格+页眉页脚);False=只处理 ``paragraph``。
        paragraph: 配合 whole_document=False 使用,指定要改的段落下标。
        out_path: 另存路径;留空覆盖原文件。

    Returns:
        {"success", "path", "total": 命中总数, "detail": [...]}
    """
    try:
        doc = _open(file_path)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"打开失败: {e}"}

    if not isinstance(replacements, dict) or not replacements:
        return {"success": False, "error": "replacements 必须是非空对象,如 {\"旧文字\":\"新文字\"}"}

    from docx.text.run import Run

    def replace_in_paragraph(p, mapping: dict) -> dict:
        """在一个段落内做**一次性**多方替换。

        为什么不能一个个模式轮流替换:
        先替 A 再替 B 时,A 写入的新文字可能被 B 再次命中,导致结果不可预测
        (实测 ``{"5":"10", "500":"2000"}`` 会把 ``500`` 先变成 ``1000``,
        再找不到 ``500``)。正确做法是**单次扫描**:在原文本上一次性找出所有
        命中(长串优先,避免 ``500`` 被 ``5`` 抢走),按位置直接生成结果。

        Word 会把一句话切成多个 run,要找的串很可能横跨好几个 —— 直接把某个
        run 的 text 改掉会漏匹配。做法:先把各 run 文本拼成整段,在整段上定位,
        再按「新文本写回第一个被命中 run、其余 run 只删不写」的方式回填,
        这样每个 run 的 rPr(格式)都不动。

        Args:
            p: python-docx Paragraph。
            mapping: 旧串到新串的映射。

        Returns:
            {旧串: 命中次数}。
        """
        runs = list(p.runs)
        if not runs or not mapping:
            return {}

        full = "".join(r.text or "" for r in runs)
        if not full:
            return {}

        # 长串优先匹配:否则 {"5":..., "500":...} 里 500 会被 5 抢走
        keys = sorted((k for k in mapping if k), key=len, reverse=True)

        # 一次性扫描出所有命中区间 (start, end, key)
        hits: list[tuple[int, int, str]] = []
        i = 0
        n = len(full)
        while i < n:
            for k in keys:
                if full.startswith(k, i):
                    hits.append((i, i + len(k), k))
                    i += len(k)
                    break
            else:
                i += 1

        if not hits:
            return {}

        counts: dict[str, int] = {}
        for _, _, k in hits:
            counts[k] = counts.get(k, 0) + 1

        # 把原全文按命中切成「保留段」与「替换段」
        # 每段带一个归属:它来自哪个 run 的哪个区间(保留段),
        # 或者是某个命中(替换段 → 归给命中起点所在的 run)。
        segs: list[tuple[int, str, bool]] = []  # (run_index, text, is_new)
        old_pos = 0
        run_bounds: list[tuple[int, int]] = []
        for r in runs:
            ln = len(r.text or "")
            run_bounds.append((old_pos, old_pos + ln))
            old_pos += ln

        def run_of(pos: int) -> int:
            """原全文位置 pos 属于哪个 run(越界归最后一个)。"""
            for ri, (s, e) in enumerate(run_bounds):
                if s <= pos < e:
                    return ri
            return len(runs) - 1

        last = 0
        for s, e, k in hits:
            if s > last:
                # 保留段可能横跨多个 run,按 run 边界再切细
                p0 = last
                while p0 < s:
                    ri = run_of(p0)
                    rs, re_ = run_bounds[ri]
                    nxt = min(s, re_)
                    segs.append((ri, full[p0:nxt], False))
                    p0 = nxt
            segs.append((run_of(s), str(mapping[k]), True))
            last = e
        p0 = last
        while p0 < len(full):
            ri = run_of(p0)
            rs, re_ = run_bounds[ri]
            nxt = min(len(full), re_)
            segs.append((ri, full[p0:nxt], False))
            p0 = nxt

        # 每个 run 拿到属于自己的所有片段(替换段归命中起点所在 run → 继承它的格式)
        buckets: list[list[str]] = [[] for _ in runs]
        for ri, txt, _is_new in segs:
            buckets[ri].append(txt)

        for r, parts in zip(runs, buckets):
            r.text = "".join(parts)

        return counts

    detail: list[str] = []
    total = 0

    if whole_document:
        targets = list(_iter_all_paragraphs(doc))
    else:
        if paragraph is None:
            return {"success": False, "error": "whole_document=False 时必须给 paragraph 下标"}
        try:
            targets = [(int(paragraph), _find_paragraph(doc, int(paragraph)))]
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    for idx, p in targets:
        counts = replace_in_paragraph(p, {str(k): v for k, v in replacements.items()})
        for k, cnt in counts.items():
            total += cnt
            detail.append(f"段落[{idx}] {k!r} -> {str(replacements[k])!r} ×{cnt}")

    if total == 0:
        return {
            "success": False,
            "error": "没有找到要替换的文字。注意:跨段落/跨表格单元格的文字匹配不到,"
            "且必须完全一致(含全角/半角、空格)。可先用 inspect_docx 或 doc_to_markdown 确认真实文字。",
            "total": 0,
        }

    if out_path:
        ok, resolved_out = _guard(out_path)
        if not ok:
            return {"success": False, "error": resolved_out}
        target_path = resolved_out
    else:
        target_path = os.path.abspath(file_path)
    try:
        doc.save(target_path)
    except Exception as e:
        return {"success": False, "error": f"保存失败: {e}"}

    return {"success": True, "path": target_path, "total": total, "detail": detail}


DOCX_EDIT_TOOLS_SCHEMAS = {
    "inspect_docx": {
        "risk_channel": "read",
        "func": inspect_docx,
        "description": (
            "列出 .docx 的段落/表格/页眉结构及其样式(字号、颜色、字体、加粗、对齐、"
            "缩进、行距、底纹),并给每个段落一个下标。"
            "**要修改已有 Word 文档前必须先调它** —— 否则不知道现在是什么格式、"
            "也不知道该改哪一段。注意:doc_to_markdown 只给文字、样式全丢,不能用来改格式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": ".docx 的绝对路径"},
                "max_items": {
                    "type": "integer",
                    "description": f"最多列出多少个段落,默认 {INSPECT_MAX_ITEMS}",
                },
            },
            "required": ["file_path"],
        },
    },
    "format_docx": {
        "risk_channel": "write",
        "func": format_docx,
        "description": (
            "原地修改 .docx 里某一段或某一段内某个 run 的格式,**其余内容与样式一律不动**。"
            "只改显式传的参数,没传的保持原样。"
            "先用 inspect_docx 拿到段落下标;想只改一句话里的几个字就再指定 run 下标。"
            "这是「改而不坏」的正确做法 —— 不要用 md_to_docx 重写,那会清空原有样式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": ".docx 绝对路径"},
                "paragraph": {"type": "integer", "description": "段落下标(由 inspect_docx 给出)"},
                "run": {
                    "type": "integer",
                    "description": "run 下标;留空=该段全部 run。只改段落里某几个字时用它",
                },
                "size": {"type": "number", "description": "字号(磅),如 12 / 14 / 22"},
                "color": {"type": "string", "description": "字体颜色,6 位十六进制如 FF0000;auto=自动色"},
                "font": {"type": "string", "description": "字体名,如 SimHei / 微软雅黑 / Times New Roman"},
                "bold": {"type": "boolean", "description": "加粗"},
                "italic": {"type": "boolean", "description": "斜体"},
                "underline": {"type": "boolean", "description": "下划线"},
                "strike": {"type": "boolean", "description": "删除线"},
                "align": {
                    "type": "string",
                    "enum": ["left", "center", "right", "justify", "distribute"],
                    "description": "对齐方式(作用于整段)",
                },
                "first_line_indent": {"type": "number", "description": "首行缩进(磅)"},
                "left_indent": {"type": "number", "description": "左缩进(磅)"},
                "line_spacing": {"type": "number", "description": "行距倍数,如 1.5"},
                "space_before": {"type": "number", "description": "段前间距(磅)"},
                "space_after": {"type": "number", "description": "段后间距(磅)"},
                "shading": {
                    "type": "string",
                    "description": "段落底纹色,6 位十六进制如 FFF2CC;none=清除底纹",
                },
                "out_path": {"type": "string", "description": "另存路径;留空=覆盖原文件"},
            },
            "required": ["file_path", "paragraph"],
        },
    },
    "replace_docx_text": {
        "risk_channel": "write",
        "func": replace_docx_text,
        "description": (
            "在 .docx 里批量替换文字,**逐字保留原有格式**(字体/字号/颜色/加粗都不变)。"
            "适合「把合同里的甲方名称全换掉」「更新报告里的数字」这类需求。"
            "只替换文字、不动排版;要改格式请用 format_docx。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": ".docx 绝对路径"},
                "replacements": {
                    "type": "object",
                    "description": '替换映射,如 {"旧公司名":"新公司名","2024":"2025"}',
                    "additionalProperties": {"type": "string"},
                },
                "whole_document": {
                    "type": "boolean",
                    "description": "True=全文档(正文+表格+页眉页脚),默认 True",
                },
                "paragraph": {
                    "type": "integer",
                    "description": "whole_document=False 时指定只改哪一段",
                },
                "out_path": {"type": "string", "description": "另存路径;留空=覆盖原文件"},
            },
            "required": ["file_path", "replacements"],
        },
    },
}
