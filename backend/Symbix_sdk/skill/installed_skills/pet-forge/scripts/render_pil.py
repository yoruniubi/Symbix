"""纯 Pillow 极简 SVG 渲染器(零额外依赖,cairosvg 的可选替代)。

针对 pet-forge rig 的受限子集实现:
- 元素: g / circle / ellipse / rect / line / polyline / polygon / path
- path 命令: M L H V C S Q T A Z(绝对 + 相对,支持隐式重复参数)
- 样式: fill / stroke / stroke-width / stroke-linecap / opacity / fill-opacity / stroke-opacity
- transform(g 级): translate / scale / rotate / matrix
- 颜色: #hex / #RGB / rgb() / rgba() / 常用命名色 / none

其他 SVG 特性(滤镜、渐变、文字、foreignObject 等)一律忽略 → 输出“大概差不多”的
栅格图,对烘焙与像素量化足够。要更精细请自己装 cairosvg(本渲染器不依赖它)。
"""
from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw

    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

_CMD_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_PAINT_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")

_NAMED = {
    "white": "#FFFFFF", "black": "#000000", "red": "#FF0000", "green": "#008000",
    "blue": "#0000FF", "gray": "#808080", "grey": "#808080", "silver": "#C0C0C0",
    "yellow": "#FFFF00", "orange": "#FFA500", "purple": "#800080", "pink": "#FFC0CB",
    "brown": "#A52A2A", "gold": "#FFD700", "cyan": "#00FFFF", "magenta": "#FF00FF",
    "transparent": "none", "none": "none",
}


# ── 颜色 ──────────────────────────────────────────────────────
# 未解析的颜色变量(只警告一次):正常情况下烘焙前会把主题色注入根 style,
# 真出现说明 rig 用了根 style 没声明的 --pet-*,然后会静默变黑。
_WARNED_VARS: set[str] = set()


def parse_color(v: Optional[str], alpha: float = 1.0) -> Optional[tuple[int, int, int, int]]:
    if not v:
        return None
    v = v.strip().lower()
    if v.startswith("var("):
        if v not in _WARNED_VARS:
            _WARNED_VARS.add(v)
            print(
                f"[warn] 颜色变量未解析: {v} → 兜底黑。"
                "请把它写进 <svg> 根 style,或通过调色板注入(烘焙会自动补)。",
                file=sys.stderr,
            )
        return (0, 0, 0, int(round(255 * alpha)))
    if v in _NAMED:
        v = _NAMED[v]
    if v == "none":
        return None
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(round(255 * alpha)))
            except ValueError:
                pass
    m = _PAINT_RE.match(v)
    if m:
        if m.group(1) in ("rgb", "rgba"):
            try:
                parts = [p.strip() for p in m.group(2).split(",")]
                if len(parts) >= 3:
                    r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
                    a = float(parts[3]) if len(parts) > 3 else 1.0
                    return (r, g, b, int(round(255 * alpha * a)))
            except ValueError:
                pass
    return (0, 0, 0, int(round(255 * alpha)))  # 兜底黑色


# ── 变换 ──────────────────────────────────────────────────────
def _affine_apply(pt, a, b, c, d, e, f):
    x, y = pt
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(t: Optional[str]) -> list:
    """解析 transform → 仿射列表 [(a,b,c,d,e,f),...](SVG 顺序)。"""
    out = []
    if not t:
        return out
    for m in _PAINT_RE.finditer(t):
        name = m.group(1).lower()
        nums = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", m.group(2))]
        if name == "translate" and nums:
            tx, ty = nums[0], nums[1] if len(nums) > 1 else 0
            out.append((1, 0, 0, 1, tx, ty))
        elif name == "scale" and nums:
            sx, sy = nums[0], nums[1] if len(nums) > 1 else nums[0]
            out.append((sx, 0, 0, sy, 0, 0))
        elif name == "rotate" and nums:
            ang = math.radians(nums[0])
            cx, cy = (nums[1], nums[2]) if len(nums) >= 3 else (0, 0)
            cos, sin = math.cos(ang), math.sin(ang)
            # x' = cos(x-cx) - sin(y-cy) + cx
            out.append((cos, sin, -sin, cos, cx - cos * cx + sin * cy, cy - sin * cx - cos * cy))
        elif name == "matrix" and len(nums) == 6:
            out.append((nums[0], nums[1], nums[2], nums[3], nums[4], nums[5]))
    return out


def apply_transforms(pt, mats):
    """把仿射列表作用到点上。

    SVG 语义:transform 列表从左到右相乘(x' = M1·M2·…·Mn·x),即**最后一项先作用于点**。
    mats 是按「祖先 → 子节点」顺序累积的,因此必须反向应用;正序应用会等价于
    Mn·…·M2·M1,使 translate+scale(镜像)与嵌套 g 的位移全部算错(部件飞出画布)。
    """
    for m in reversed(mats):
        pt = _affine_apply(pt, *m)
    return pt


# ── path 解析 ─────────────────────────────────────────────────
def _tokenize(d: str) -> list:
    tokens = []
    i, n = 0, len(d)
    while i < n:
        ch = d[i]
        if ch.isspace() or ch == ",":
            i += 1
            continue
        if _CMD_RE.match(ch):
            tokens.append(ch)
            i += 1
            continue
        m = _NUM_RE.match(d, i)
        if m:
            tokens.append(float(m.group()))
            i = m.end()
            continue
        i += 1  # 未知字符跳过
    return tokens


def _ang(ux, uy, vx, vy):
    dot = ux * vx + uy * vy
    lensq = (ux * ux + uy * uy) * (vx * vx + vy * vy)
    if lensq <= 0:
        return 0.0
    cosv = max(-1.0, min(1.0, dot / math.sqrt(lensq)))
    a = math.acos(cosv)
    if ux * vy - uy * vx < 0:
        a = -a
    return a


def _arc_points(x1, y1, rx, ry, phi_deg, fA, fS, x2, y2, n=24):
    """SVG endpoint→center 参数化,返回点列表。"""
    if x1 == x2 and y1 == y2:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(phi_deg % 360)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos * dx + sin * dy
    y1p = -sin * dx + cos * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den > 0 else 0.0
    if fA == fS:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    cx = cos * cxp - sin * cyp + (x1 + x2) / 2.0
    cy = sin * cxp + cos * cyp + (y1 + y2) / 2.0
    th1 = _ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = _ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fS and dth > 0:
        dth -= 2 * math.pi
    elif fS and dth < 0:
        dth += 2 * math.pi
    pts = []
    steps = max(4, int(abs(dth) / (2 * math.pi) * n))
    for k in range(steps + 1):
        th = th1 + dth * k / steps
        pts.append((cx + rx * math.cos(th) * cos - ry * math.sin(th) * sin,
                    cy + rx * math.cos(th) * sin + ry * math.sin(th) * cos))
    return pts


def _curve_points(p0, p1, p2, p3, quad, n=24):
    pts = []
    for k in range(n + 1):
        t = k / n
        if quad:
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        else:
            u = 1 - t
            x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
            y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


def parse_path(d: str) -> list:
    """d → [{'points':[(x,y)...], 'closed': bool}, ...]"""
    toks = _tokenize(d)
    subpaths = []
    pts = []
    closed = False
    i = 0
    x = y = 0.0
    sx = sy = 0.0
    prev_cmd = None
    prev_ctrl = None  # 上一个曲线控制点(相对 S/T 反射)

    def flush():
        nonlocal pts, closed
        if pts:
            subpaths.append({"points": list(pts), "closed": closed})
        pts = []
        closed = False

    n_tokens = len(toks)
    while i < n_tokens:
        t = toks[i]
        if isinstance(t, str):
            cmd = t
            i += 1
            prev_cmd = cmd
            prev_ctrl = None
            continue
        if prev_cmd is None:
            prev_cmd = "L"
        cmd = prev_cmd.upper()
        rel = prev_cmd.islower()

        if cmd in "ML":
            if i + 1 >= n_tokens:
                break
            x2 = t + (x if rel else 0)
            y2 = toks[i + 1] + (y if rel else 0)
            i += 2
            if cmd == "M":
                flush()
                sx, sy = x2, y2
            pts.append((x2, y2))
            x, y = x2, y2
            if cmd == "M":
                prev_cmd = "L"  # 隐式后续为线段
                rel = False
        elif cmd in "HV":
            v = t
            i += 1
            if cmd == "H":
                px, py = (x + v if rel else v), y
            else:
                px, py = x, (y + v if rel else v)
            pts.append((px, py))
            x, y = px, py
        elif cmd in "CSQT":
            need = 6 if cmd in "CS" else 4
            if i + need - 1 >= n_tokens:
                break
            args = [t] + toks[i + 1:i + need]
            i += need
            p0 = (x, y)
            if cmd == "C":
                p1 = (args[0] + (p0[0] if rel else 0), args[1] + (p0[1] if rel else 0))
                p2 = (args[2] + (p0[0] if rel else 0), args[3] + (p0[1] if rel else 0))
                p3 = (args[4] + (p0[0] if rel else 0), args[5] + (p0[1] if rel else 0))
                seg = _curve_points(p0, p1, p2, p3, quad=False)
                prev_ctrl = p2
            elif cmd == "S":
                if prev_ctrl is not None and prev_cmd.upper() in "CS":
                    p1 = (2 * p0[0] - prev_ctrl[0], 2 * p0[1] - prev_ctrl[1])
                else:
                    p1 = p0
                p2 = (args[0] + (p0[0] if rel else 0), args[1] + (p0[1] if rel else 0))
                p3 = (args[2] + (p0[0] if rel else 0), args[3] + (p0[1] if rel else 0))
                seg = _curve_points(p0, p1, p2, p3, quad=False)
                prev_ctrl = p2
            elif cmd == "Q":
                p1 = (args[0] + (p0[0] if rel else 0), args[1] + (p0[1] if rel else 0))
                p2 = (args[2] + (p0[0] if rel else 0), args[3] + (p0[1] if rel else 0))
                seg = _curve_points(p0, p1, p2, None, quad=True)
                prev_ctrl = p1
            else:  # T
                if prev_ctrl is not None and prev_cmd.upper() in "QT":
                    p1 = (2 * p0[0] - prev_ctrl[0], 2 * p0[1] - prev_ctrl[1])
                else:
                    p1 = p0
                p2 = (args[0] + (p0[0] if rel else 0), args[1] + (p0[1] if rel else 0))
                seg = _curve_points(p0, p1, p2, None, quad=True)
                prev_ctrl = p1
            pts.extend(seg)
            x, y = seg[-1]
        elif cmd == "A":
            if i + 6 >= n_tokens:
                break
            rx, ry, phi, fA, fS = float(t), float(toks[i + 1]), float(toks[i + 2]), bool(toks[i + 3]), bool(toks[i + 4])
            x2l = toks[i + 5]
            if i + 6 < n_tokens and isinstance(toks[i + 6], (int, float)):
                y2l = toks[i + 6]
                i += 7
            else:
                break
            x2 = x + x2l if rel else x2l
            y2 = y + y2l if rel else y2l
            seg = _arc_points(x, y, rx, ry, phi, fA, fS, x2, y2)
            if not seg:
                seg = [(x2, y2)]
            pts.extend(seg)
            x, y = x2, y2
        elif cmd == "Z":
            if pts:
                pts.append((sx, sy))
            closed = True
            flush()
            x, y = sx, sy
            i += 1
        else:
            break
    flush()
    return subpaths


# ── 形状采样 ─────────────────────────────────────────────────
def _num(attrs, key, default=0.0):
    v = attrs.get(key)
    if v is None:
        return default
    m = re.match(r"[-+]?(?:\d+\.?\d*|\.\d+)", str(v).strip())
    return float(m.group()) if m else default


def shape_to_subpaths(tag: str, attrs) -> Optional[list]:
    subpaths = []
    if tag == "circle":
        cx, cy, r = _num(attrs, "cx"), _num(attrs, "cy"), _num(attrs, "r")
        if r > 0:
            pts = [(cx + r * math.cos(2 * math.pi * k / 32), cy + r * math.sin(2 * math.pi * k / 32)) for k in range(32)]
            subpaths.append({"points": pts, "closed": True})
    elif tag == "ellipse":
        cx, cy, rx, ry = _num(attrs, "cx"), _num(attrs, "cy"), _num(attrs, "rx"), _num(attrs, "ry")
        if rx > 0 and ry > 0:
            pts = [(cx + rx * math.cos(2 * math.pi * k / 32), cy + ry * math.sin(2 * math.pi * k / 32)) for k in range(32)]
            subpaths.append({"points": pts, "closed": True})
    elif tag == "rect":
        x, y = _num(attrs, "x"), _num(attrs, "y")
        w, h = _num(attrs, "width"), _num(attrs, "height")
        rx = _num(attrs, "rx")
        ry = _num(attrs, "ry") if attrs.get("ry") is not None else rx
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if rx > 0 and ry > 0:
            # 圆角矩形:四条边 + 四角圆弧采样
            arc = 10
            pts = []

            def corner(cx, cy, a0, a1):
                for k in range(arc + 1):
                    a = math.radians(a0 + (a1 - a0) * k / arc)
                    pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))

            corner(x + rx, y + ry, -90, 0)
            corner(x + w - rx, y + ry, 0, 90)
            corner(x + w - rx, y + h - ry, 90, 180)
            corner(x + rx, y + h - ry, 180, 270)
        else:
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        subpaths.append({"points": pts, "closed": True})
    elif tag == "line":
        x1, y1, x2, y2 = _num(attrs, "x1"), _num(attrs, "y1"), _num(attrs, "x2"), _num(attrs, "y2")
        subpaths.append({"points": [(x1, y1), (x2, y2)], "closed": False})
    elif tag in ("polyline", "polygon"):
        pts = []
        for m in re.finditer(r"[-+]?(?:\d+\.?\d*|\.\d+)[,\s]+[-+]?(?:\d+\.?\d*|\.\d+)", attrs.get("points", "")):
            a, b = m.group().split(",") if "," in m.group() else m.group().split()
            pts.append((float(a), float(b)))
        if pts:
            subpaths.append({"points": pts, "closed": tag == "polygon"})
    elif tag == "path":
        subpaths = parse_path(attrs.get("d", ""))
    return subpaths or None


# ── 渲染 ──────────────────────────────────────────────────────
def _local(tag: str) -> str:
    return tag.split("}")[-1]


_CSS_VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")


def _extract_css_vars(root: ET.Element) -> dict[str, str]:
    """从 <svg> 根节点的 style 属性提取 CSS 变量表(--pet-*: #hex;...)。"""
    out: dict[str, str] = {}
    style_attr = root.get("style") if isinstance(root, ET.Element) else None
    if not style_attr:
        return out
    for kv in style_attr.split(";"):
        if ":" not in kv:
            continue
        k, v = kv.split(":", 1)
        k = k.strip()
        if k.startswith("--") and v.strip():
            out[k] = v.strip()
    return out


def _expand_css_vars(style: dict, css_vars: dict[str, str]) -> dict:
    """把 style 值里的 var(--x) 替换为实际色值(缺失时保留原值,交给 parse_color 姰底)。"""
    if not css_vars:
        return style
    out = dict(style)
    for k, v in style.items():
        if isinstance(v, str) and "var(" in v:
            def repl(m):
                var_name = m.group(1)
                fallback = m.group(2)
                return css_vars.get(var_name, (fallback if fallback else m.group(0)))
            out[k] = _CSS_VAR_RE.sub(repl, v)
    return out


def _merge_style(parent: dict, attrs: dict) -> dict:
    st = dict(parent)
    for k, v in attrs.items():
        if k == "style":
            for kv in v.split(";"):
                if ":" in kv:
                    key, val = kv.split(":", 1)
                    st[key.strip()] = val.strip()
        else:
            st[k] = v
    return st


def _render_node(node, mats, inherit, draw, geom, css_vars=None):
    tag = _local(node.tag)
    attrs = {k: v for k, v in node.attrib.items()}
    style = _merge_style(inherit, attrs)
    mats = mats + [m for m in parse_transform(attrs.get("transform"))]

    if tag == "g":
        for child in node:
            _render_node(child, mats, style, draw, geom, css_vars)
        return
    if tag in ("svg", "defs", "metadata", "title", "desc", "style", "script"):
        for child in node:
            if tag != "svg":
                continue
            _render_node(child, mats, style, draw, geom, css_vars)
        return

    subpaths = shape_to_subpaths(tag, attrs)
    if not subpaths:
        return
    if not _HAS_PIL:
        return

    if css_vars:
        style = _expand_css_vars(style, css_vars)
    opacity = _num(attrs, "opacity", 1.0) if attrs.get("opacity") is not None \
        else (_num(style, "opacity", 1.0) if style.get("opacity") is not None else 1.0)
    fill = parse_color(style.get("fill"), opacity)
    if style.get("fill-opacity") is not None:
        fo = max(0.0, min(1.0, _num(style, "fill-opacity", 1.0)))
        if fill:
            fill = (fill[0], fill[1], fill[2], int(round(fill[3] * fo)))
    stroke = parse_color(style.get("stroke"), opacity)
    if style.get("stroke-opacity") is not None:
        so = max(0.0, min(1.0, _num(style, "stroke-opacity", 1.0)))
        if stroke:
            stroke = (stroke[0], stroke[1], stroke[2], int(round(stroke[3] * so)))
    # 若都无颜色,跳过
    if not fill and not stroke:
        return
    sw = _num(style, "stroke-width", 1.0)

    ox, oy, sxf, syf = geom["ox"], geom["oy"], geom["sx"], geom["sy"]
    dx, dy = geom.get("dx", 0.0), geom.get("dy", 0.0)
    pixel = bool(geom.get("pixel"))
    for sph in subpaths:
        pts = [apply_transforms(p, mats) for p in sph["points"]]
        if len(pts) < 2:
            continue
        pix = [((px - ox) * sxf + dx, (py - oy) * syf + dy) for px, py in pts]
        if pixel:
            # 像素画板模式:坐标吸附到整数格(取整交给绘制层,避免四处改几何)
            pix = [(float(round(px)), float(round(py))) for px, py in pix]
        if fill and len(pix) >= 3:
            draw.polygon(pix, fill=fill)
        if stroke:
            line_pts = list(pix)
            if sph["closed"] and line_pts:
                line_pts.append(line_pts[0])
            try:
                draw.line(line_pts, fill=stroke, width=max(1, int(round(sw * geom["scale"]))))
            except TypeError:
                draw.line(line_pts, fill=stroke)


def _palette_from_css_vars(root) -> list[tuple[int, int, int, int]]:
    """从根节点 style 的 --pet-* 变量解析出调色板(像素模式量化用)。"""
    uniq: list[tuple[int, int, int, int]] = []
    for value in _extract_css_vars(root).values():
        c = parse_color(value, 1.0)
        if c is None or c[3] <= 0:
            continue
        rgb = (c[0], c[1], c[2], 255)
        if rgb not in uniq:
            uniq.append(rgb)
    return uniq


def _quantize_palette(img, palette: list[tuple[int, int, int, int]]) -> None:
    """把画布颜色吸附到最近的调色板色(受限调色板 = 像素风的一半)。

    只改 RGB,保留原本的 alpha;带缓存避免 4 万像素 × 调色板大小的重复计算。
    """
    if not palette:
        return
    px = img.load()
    w, h = img.size
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            key = (r, g, b)
            hit = cache.get(key)
            if hit is None:
                best = palette[0]
                best_d = None
                for pc in palette:
                    d = (r - pc[0]) ** 2 + (g - pc[1]) ** 2 + (b - pc[2]) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = pc, d
                hit = (best[0], best[1], best[2])
                cache[key] = hit
            px[x, y] = (hit[0], hit[1], hit[2], a)


def svg_to_png(
    svg_text: str,
    out_path: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: int = 2,
    background: Optional[tuple[int, int, int, int]] = None,
    resample: int = 3,
    fit: str = "contain",
    pixel: bool = False,
    palette: Optional[list[tuple[int, int, int, int]]] = None,
) -> Optional[bytes]:
    """渲染 SVG 文本 → PNG bytes。

    - background: None = 透明;传 (r,g,b,a) 则填充(如白底预览)。
    - resample: 降采样器(默认 Image.LANCZOS=1);像素风传 Image.NEAREST=0 保留硬边。
    - fit: contain = 等比缩放并居中(默认)。非等比拉伸(viewBox 200x200 → 192x208,
      sx=0.96/sy=1.04)会把像素风压扁、整数坐标落到非整数像素 → 边缘毛刺与抖动;
      传 "stretch" 可恢复旧行为。
    - pixel: 像素画板模式。viewBox 就是画板(1 用户单位 = 1 格),先在 1:1 画布上按整数格
      栅格化(无抗锯齿),把颜色吸附到 palette(默认取根 style 的 --pet-* 变量),
      最后用 NEAREST 缩放进帧尺寸。此时 scale/resample 不再起作用。
    - palette: 显式调色板(像素模式量化用);None = 从 CSS 变量推导。
    scale 超采样抗锯齿(像素风建议 scale=1 + NEAREST)。失败返回 None。
    """
    if not _HAS_PIL:
        return None
    try:
        root = ET.fromstring(svg_text)
    except Exception:
        return None
    try:
        vb = [float(x) for x in re.split(r"[ ,]+", (root.get("viewBox") or "").strip()) if x]
        vbw = vb[2] if len(vb) >= 4 else 200.0
        vbh = vb[3] if len(vb) >= 4 else 200.0
        ox, oy = (vb[0], vb[1]) if len(vb) >= 4 else (0.0, 0.0)
        if vbw <= 0:
            vbw = 200.0
        if vbh <= 0:
            vbh = 200.0
        w = int(width or vbw)
        h = int(height or vbh)
        bg = background if background is not None else (0, 0, 0, 0)
        if pixel:
            # 画板 1:1 栅格化(整数格,无 AA)→ 调色板量化 → NEAREST 缩进帧
            board = Image.new("RGBA", (max(1, int(round(vbw))), max(1, int(round(vbh)))), bg)
            geom = {"ox": ox, "oy": oy, "sx": 1.0, "sy": 1.0,
                    "dx": 0.0, "dy": 0.0, "scale": 1, "pixel": True}
            css_vars = _extract_css_vars(root)
            for child in list(root):
                _render_node(child, [], {}, ImageDraw.Draw(board), geom, css_vars)
            _quantize_palette(board, palette or _palette_from_css_vars(root))
            s = min(w / vbw, h / vbh)
            dw, dh = max(1, int(round(vbw * s))), max(1, int(round(vbh * s)))
            img = Image.new("RGBA", (w, h), bg)
            img.paste(board.resize((dw, dh), Image.NEAREST), ((w - dw) // 2, (h - dh) // 2))
            import io as _io
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            if out_path:
                Path(out_path).write_bytes(data)
            return data
        img = Image.new("RGBA", (int(w * scale), int(h * scale)), bg)
        draw = ImageDraw.Draw(img)
        if fit == "stretch":
            sx = (w * scale) / vbw
            sy = (h * scale) / vbh
            dx = dy = 0.0
        else:
            # 等比 contain + 居中:禁止非等比拉伸,保留像素风比例
            sx = sy = min((w * scale) / vbw, (h * scale) / vbh)
            dx = ((w * scale) - vbw * sx) / 2.0
            dy = ((h * scale) - vbh * sy) / 2.0
        geom = {"ox": ox, "oy": oy, "sx": sx, "sy": sy, "dx": dx, "dy": dy, "scale": scale}
        css_vars = _extract_css_vars(root)
        for child in list(root):
            _render_node(child, [], {}, draw, geom, css_vars)
        if scale != 1:
            img = img.resize((w, h), resample)
        import io as _io
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        if out_path:
            Path(out_path).write_bytes(data)
        return data
    except Exception:
        return None