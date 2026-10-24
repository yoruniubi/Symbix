"""严格校验 base SVG rig。返回结构化错误列表（不是 bool）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# 允许作为脚本直接运行
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    REQUIRED_PARTS,
    VIEWBOX_ACCEPTED,
    VIEWBOX_CANVAS,
    VIEWBOX_LEGACY,
    _HARD_COLOR_RE,
    _ON_ATTR_RE,
    read_text,
)

# SVG 默认命名空间
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _attr(el: ET.Element, name: str) -> str | None:
    if name in el.attrib:
        return el.attrib[name]
    # namespaced
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return None


def _has_transform_origin(el: ET.Element) -> bool:
    if _attr(el, "transform-origin"):
        return True
    style = _attr(el, "style") or ""
    return "transform-origin" in style.replace(" ", "")


def _iter_all(root: ET.Element):
    yield root
    for child in root.iter():
        if child is not root:
            yield child


_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# 像素画板契约 ──────────────────────────────────────
# 取整检查的几何属性(坐标为格数,必须是整数)
_PIXEL_INT_ATTRS: dict[str, tuple[str, ...]] = {
    "circle": ("cx", "cy", "r"),
    "ellipse": ("cx", "cy", "rx", "ry"),
    "rect": ("x", "y", "width", "height", "rx", "ry"),
    "line": ("x1", "y1", "x2", "y2"),
}
# 渲染器不支持 → 用了就只有空白/黑块
_PIXEL_UNSUPPORTED_TAGS = (
    "lineargradient",
    "radialgradient",
    "pattern",
    "filter",
    "mask",
    "image",
)
_CURVE_CMD_RE = re.compile(r"[CcSsQqTtAa]")


def _is_int_num(raw: str) -> bool:
    try:
        return float(raw) % 1 == 0
    except (TypeError, ValueError):
        return True


def _pixel_contract(root: ET.Element) -> list[dict[str, Any]]:
    """像素画板契约:viewBox 就是画板,每个整数坐标 = 一个像素格,逐格填色。

    推荐画板 = 帧 cell(192x208):1 格 = 1 帧像素,零重采样;
    老式 200x200 画板仍可用,但会 0.96 倍缩进 192x208(约丢 4% 行列)→ 降级为 warning。
    error = 一定破坏像素风或根本渲染不出来;warning = 能渲染但不够像素/会被裁。
    """
    out: list[dict[str, Any]] = []
    vb = []
    for x in re.split(r"[ ,]+", (_attr(root, "viewBox") or "").strip()):
        try:
            vb.append(float(x))
        except ValueError:
            vb.append(0.0)
    vbw = vb[2] if len(vb) >= 4 and vb[2] > 0 else 200.0
    vbh = vb[3] if len(vb) >= 4 and vb[3] > 0 else 200.0
    if " ".join((_attr(root, "viewBox") or "").split()) == VIEWBOX_LEGACY:
        out.append({
            "rule": "pixel_board_legacy",
            "level": "warning",
            "where": "svg@viewBox",
            "message": (f'画板 {VIEWBOX_LEGACY} 会被 0.96 倍缩进帧 192x208(约丢 4% 行列);'
                        f'新主题请改用 "{VIEWBOX_CANVAS}"(画板 = 帧尺寸,1 格 = 1 像素)'),
        })

    def add(rule: str, level: str, where: str, message: str) -> None:
        if not any(e.get("rule") == rule and e.get("where") == where for e in out):
            out.append({"rule": rule, "level": level, "where": where, "message": message})

    for el in _iter_all(root):
        tag = _local(el.tag).lower()
        if tag in _PIXEL_UNSUPPORTED_TAGS:
            add("pixel_unsupported", "error", tag,
                f"像素风不允许 <{tag}>(渲染器不实现,画出来是空的/黑的);渐变、阴影、图案请改用纯色块")
            continue
        if tag == "clippath":
            add("pixel_clip", "warning", tag,
                "<clipPath> 渲染器不实现,裁剪不会生效;像素风建议直接排版")
            continue

        # 1) 整数格坐标
        for attr in _PIXEL_INT_ATTRS.get(tag, ()):
            raw = _attr(el, attr)
            if raw is None:
                continue
            if any(not _is_int_num(n) for n in _NUM_RE.findall(raw)):
                add("pixel_grid", "error", f"{tag}@{attr}",
                    f"像素画板只能落在整数格上:{tag} 的 {attr}={raw!r} 含小数")
        if tag in ("polygon", "polyline"):
            raw = _attr(el, "points") or ""
            if any(not _is_int_num(n) for n in _NUM_RE.findall(raw)):
                add("pixel_grid", "error", f"{tag}@points", f"{tag} 的 points 含非整数坐标")
        if tag in ("path", "polygon", "polyline"):
            raw = _attr(el, "d") if tag == "path" else (_attr(el, "points") or "")
            if any(not _is_int_num(n) for n in _NUM_RE.findall(raw)):
                add("pixel_grid", "error", f"{tag}@d", f"{tag} 的坐标含小数:像素风只允许整数格(如 88 而不是 87.5)")
            # 2) 只走直线与直角(曲线在像素画板上画不出干净的台阶)
            if tag == "path" and _CURVE_CMD_RE.search(raw):
                add("pixel_curve", "error", "path@d",
                    "像素风只允许水平/垂直/斜直线的折线(路径命令限 M/L/H/V/Z),不允许 C/Q/S/T/A 曲线")

        # 3) 圆靠直线拼(会被栅格成 32 边形台阶)
        if tag in ("circle", "ellipse"):
            add("pixel_round", "warning", tag,
                f"<{tag}> 会被栅格成阶梯状的 32 边形,像素风建议用整数格矩形/折线拼出对称像素圆")
        if tag == "rect" and (_attr(el, "rx") or _attr(el, "ry")):
            add("pixel_round", "warning", f"{tag}@rx", "圆角矩形在像素风里会出现台阶;建议改用直角 + 折线倒角")

        # 4) 半透明 / 虚线 / 小数描边宽
        for attr in ("opacity", "fill-opacity", "stroke-opacity"):
            raw = _attr(el, attr)
            if raw is None:
                continue
            try:
                if float(raw) < 1:
                    add("pixel_alpha", "warning", f"{tag}@{attr}",
                        f"像素风不允许半透明({attr}={raw});颜色请直接从主题调色板取")
            except ValueError:
                pass
        style_raw = _attr(el, "style") or ""
        for key in ("opacity", "fill-opacity", "stroke-opacity"):
            m = re.search(rf"{key}\s*:\s*([0-9.]+)", style_raw)
            if m and float(m.group(1)) < 1:
                add("pixel_alpha", "warning", f"{tag}#{key}", f"像素风不允许半透明({key}={m.group(1)})")
        sw = _attr(el, "stroke-width") or (re.search(r"stroke-width\s*:\s*([0-9.]+)", style_raw) or [None, ""])[1]
        if sw and not _is_int_num(sw):
            add("pixel_stroke", "warning", f"{tag}@stroke-width",
                f"描边宽度建议用整数格({sw} → 会被取整成 1 或 2 像素)")
        if _attr(el, "stroke-dasharray"):
            add("pixel_dash", "warning", f"{tag}@stroke-dasharray", "虚线在像素风里会断成碎点,建议用实心色块")

        # 4.5) 自己的 transform / transform-origin 也应该是整数格(动画插值不算,那是逐帧采样)
        for key in ("transform-origin", "transform"):
            raw = _attr(el, key) or ""
            m = re.search(rf"{key}\s*:\s*([^;]+)", style_raw)
            if m:
                raw = raw or m.group(1)
            if key == "transform":
                # 只查 translate 的位移值;scale/rotate/matrix 不是坐标,不用对齐格点
                nums = [n for g in re.findall(r"translate\(([^)]*)\)", raw) for n in _NUM_RE.findall(g)]
            else:
                nums = [n for n in _NUM_RE.findall(raw.replace("px", " "))]
            if nums and any(not _is_int_num(n) for n in nums):
                add("pixel_grid", "error", f"{tag}@{key}",
                    f"像素画板要求整数格:{key}={raw.strip()!r} 含小数(动画插值不用手写,交给 keyframes)")

        # 5) 最小特征尺寸(小尺寸下糊成一片)
        box = _element_bbox(tag, el)
        if box:
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            if w < 2 or h < 2:
                add("pixel_min_feature", "error", tag,
                    f"特征太小({w:g}x{h:g} 格):像素风最小特征建议 2x2 格,否则缩小后直接消失")
            if x0 < -1 or y0 < -1 or x1 > vbw + 1 or y1 > vbh + 1:
                add("pixel_out_of_canvas", "warning", tag,
                    f"图形超出画板 0..{vbw:g}x{vbh:g} (bbox=({x0:g},{y0:g})-({x1:g},{y1:g})),超出部分会被裁掉")
    return out


def _element_bbox(tag: str, el: ET.Element) -> tuple[float, float, float, float] | None:
    """粗估一个图形的包围盒(只用于像素契约的「太小 / 越界」提醒)。"""
    def num(name, default=0.0):
        raw = _attr(el, name)
        m = _NUM_RE.match(raw.strip()) if raw else None
        return float(m.group()) if m else default

    if tag == "rect":
        x, y, w, h = num("x"), num("y"), num("width"), num("height")
        return (x, y, x + w, y + h)
    if tag in ("circle", "ellipse"):
        cx, cy = num("cx"), num("cy")
        rx = num("r") if tag == "circle" else num("rx")
        ry = num("r") if tag == "circle" else num("ry")
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    if tag == "line":
        return (min(num("x1"), num("x2")), min(num("y1"), num("y2")),
                max(num("x1"), num("x2")), max(num("y1"), num("y2")))
    raw = _attr(el, "d") if tag == "path" else (_attr(el, "points") or "")
    if not raw:
        return None
    nums = [float(n) for n in _NUM_RE.findall(raw)]
    if len(nums) < 2:
        return None
    xs, ys = nums[0::2], nums[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def validate_rig(svg_text: str, pixel: bool = False) -> list[dict[str, Any]]:
    """校验 SVG 文本，返回错误列表。空列表 = 通过。

    pixel=True 时额外检查「像素画板契约」(整数格 / 只走直线 / 禁渐变半透明);
    其中 level=warning 的项不算失败,调用方可单独展开展示。
    """
    errors: list[dict[str, Any]] = []
    text = (svg_text or "").strip()
    if not text:
        return [{"rule": "empty", "message": "SVG 为空"}]

    # 快速禁项（在 XML 解析前也可抓住）
    if _ON_ATTR_RE.search(text):
        errors.append(
            {
                "rule": "no_event_handlers",
                "message": "存在 on* 事件属性（禁止）",
            }
        )
    if re.search(r"javascript\s*:", text, re.I):
        errors.append(
            {
                "rule": "no_javascript_url",
                "message": "存在 javascript: URL（禁止）",
            }
        )

    try:
        # 允许 XML 声明
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return [
            {
                "rule": "xml_parse",
                "message": f"XML 解析失败: {e}",
            }
        ]

    if _local(root.tag).lower() != "svg":
        errors.append(
            {
                "rule": "root_svg",
                "where": _local(root.tag),
                "message": "根节点必须是 <svg>",
            }
        )
        return errors

    # viewBox
    vb = (_attr(root, "viewBox") or _attr(root, "viewbox") or "").strip()
    # 规范化空白
    vb_norm = " ".join(vb.split())
    if vb_norm not in VIEWBOX_ACCEPTED:
        errors.append(
            {
                "rule": "viewBox",
                "where": "svg",
                "message": (f'viewBox 必须是 "{VIEWBOX_CANVAS}"(推荐:画板 = 帧尺寸,1 格 = 1 像素)'
                            f'或老版 "{VIEWBOX_LEGACY}"，实际为 {vb!r}'),
            }
        )

    # 收集 id → element
    id_map: dict[str, ET.Element] = {}
    for el in _iter_all(root):
        eid = _attr(el, "id")
        if eid:
            id_map[eid] = el

        # forbidden tags
        tag = _local(el.tag).lower()
        if tag == "script":
            errors.append(
                {
                    "rule": "no_script",
                    "where": "script",
                    "message": "禁止 <script>",
                }
            )
        if tag == "foreignobject":
            errors.append(
                {
                    "rule": "no_foreignObject",
                    "where": "foreignObject",
                    "message": "禁止 <foreignObject>",
                }
            )
        if tag == "image":
            href = (
                _attr(el, "href")
                or el.attrib.get(f"{{{_XLINK_NS}}}href")
                or _attr(el, "xlink:href")
                or ""
            )
            href = href.strip()
            if href.startswith(("http://", "https://", "//")):
                errors.append(
                    {
                        "rule": "no_external_image",
                        "where": "image",
                        "message": f"禁止外部 image URL: {href}",
                    }
                )

        # on* on element attribs (XML parsed may lower-case differently)
        for k in el.attrib:
            lk = _local(k).lower()
            if lk.startswith("on"):
                errors.append(
                    {
                        "rule": "no_event_handlers",
                        "where": f"{tag}@{lk}",
                        "message": f"禁止事件属性 {lk}",
                    }
                )

    # 必需部件
    for part in REQUIRED_PARTS:
        el = id_map.get(part)
        if el is None:
            errors.append(
                {
                    "rule": "required_part",
                    "part": part,
                    "where": part,
                    "message": f"缺少必需部件 <g id=\"{part}\">",
                }
            )
            continue
        if _local(el.tag).lower() != "g":
            errors.append(
                {
                    "rule": "part_must_be_g",
                    "part": part,
                    "where": part,
                    "message": f"部件 {part} 必须是 <g>，实际为 <{_local(el.tag)}>",
                }
            )
        if not _has_transform_origin(el):
            errors.append(
                {
                    "rule": "transform_origin",
                    "part": part,
                    "where": part,
                    "message": f"必需部件 {part} 缺少显式 transform-origin",
                }
            )

    # 写死颜色:根节点 style 内的 CSS 变量定义(--pet-*:#hex)是主题色声明,不是写死;
    # 先从扫描文本中剔除变量定义区,再全局扫描。
    scan_text = text
    root_style = _attr(root, "style") or ""
    if root_style.strip():
        style_parts = [p.strip() for p in root_style.split(";") if p.strip()]
        kept = [kv for kv in style_parts if not (":" in kv and kv.split(":", 1)[0].strip().startswith("--"))]
        # 总是移除/替换变量定义区;root style 全部是变量时,移除整段
        scan_text = scan_text.replace(f'style="{root_style}"', f'style="{";".join(kept)}"')
    if _HARD_COLOR_RE.search(scan_text):
        # 允许在注释外；简单整体扫描
        errors.append(
            {
                "rule": "no_hardcoded_color",
                "message": "检测到写死颜色（#hex / rgb() / hsl()）。请改用 var(--pet-*)",
            }
        )

    if pixel:
        errors.extend(_pixel_contract(root))

    return errors


def validate_rig_file(path: str | Path, pixel: bool = False) -> list[dict[str, Any]]:
    return validate_rig(read_text(path), pixel=pixel)


def split_levels(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """拆出 (errors, warnings);没标 level 的旧规则一律当 error。"""
    errors = [e for e in items if e.get("level") != "warning"]
    warnings = [e for e in items if e.get("level") == "warning"]
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pet-forge base.svg rig")
    parser.add_argument("svg", help="path to SVG file")
    parser.add_argument("--json", action="store_true", help="print JSON errors")
    parser.add_argument("--smooth", action="store_true",
                        help="按平滑矢量校验(pixel 契约默认开启;老主题重烘焙时才需要)")
    args = parser.parse_args(argv)

    items = validate_rig_file(args.svg, pixel=not args.smooth)
    errors, warnings = split_levels(items)
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        for w in warnings:
            where = w.get("where") or w.get("part") or ""
            print(f"WARN [{w.get('rule')}] {where}: {w.get('message')}")
        if not errors:
            print("OK: rig valid" + (f"({len(warnings)} warning)" if warnings else ""))
        else:
            print(f"FAIL: {len(errors)} error(s)")
            for e in errors:
                where = e.get("where") or e.get("part") or ""
                print(f"  - [{e.get('rule')}] {where}: {e.get('message')}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
