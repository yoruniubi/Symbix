from __future__ import annotations
import base64
import io
from typing import Optional

try:  # pragma: no cover
    from PIL import Image  # noqa: F401

    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _hex(rgb) -> str:
    try:
        r, g, b = (int(round(c)) for c in rgb[:3])
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "#000000"


def _pil_from_bytes(raw: bytes) -> Optional["Image.Image"]:
    if not _HAS_PIL:
        return None
    try:
        from PIL import Image

        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None


def extract_palette_bytes(raw: bytes, n: int = 6) -> Optional[list[str]]:
    """从图片字节提取主色,返回 hex 列表(降序重要性)。失败返回 None。

    纯 Pillow 中位切分 quantize,无额外依赖。
    """
    if not raw or not _HAS_PIL:
        return None
    try:
        img = _pil_from_bytes(raw)
        if img is None:
            return None
        size = max(img.size)
        if size > 256:
            img = img.resize(
                (max(1, int(img.width * 256 / size)), max(1, int(img.height * 256 / size))),
                Image.LANCZOS,
            )
        # Pillow 7 兼容:只用 colors + method,不传 dither(避免 Dither 枚举版本差异)
        q = img.quantize(colors=n, method=Image.MEDIANCUT)
        counts = q.getcolors()
        if not counts:
            return None
        counts.sort(reverse=True)
        pal = q.getpalette() or []
        out: list[str] = []
        for _, idx in counts[:n]:
            rgb = pal[idx * 3 : idx * 3 + 3]
            if len(rgb) == 3:
                out.append(_hex(rgb))
        return out or None
    except Exception:
        return None


def extract_palette_b64(b64: str, n: int = 6) -> Optional[list[str]]:
    """从裸 base64 / dataURL 提取主色。失败返回 None。"""
    if not b64:
        return None
    try:
        if b64.startswith("data:"):
            b64 = b64.split(",", 1)[-1]
        raw = base64.b64decode(b64)
        if not raw:
            return None
        return extract_palette_bytes(raw, n=n)
    except Exception:
        return None


def palette_to_hint(hexes: Optional[list[str]]) -> str:
    """把主色列表转成拼进 prompt 的文本片段。无主色时返回空串。"""
    if not hexes:
        return ""
    return "主色:" + ",".join(hexes[:6])


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (128, 128, 128)


def colors_to_pet_slots(hexes: Optional[list[str]]) -> dict[str, str]:
    """把提取色 hex 列表映射到 6 个 --pet-* 槽位。

    原则:过多的提取色里,
    - primary = 第 1 个(最醒目主色)
    - secondary = 第 2 个
    - accent = 剩余色里饱和度最高(点缀);没有就用默认桃色
    - eye = 全色中最亮(眼白);全色都暗则用默认白
    - line = 全色中最暗(描边);全色都亮则用默认近黑
    - pupil = 次暗(瞳孔);兜底默认近黑
    避免把亮色硬塞给 line/pupil(那是错误的语义角色)。
    """
    if not hexes:
        return {}
    colors = [h for h in hexes if h]
    if not colors:
        return {}

    def lum(c):
        r, g, b = _hex_to_rgb(c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def sat(c):
        r, g, b = _hex_to_rgb(c)
        mx, mn = max(r, g, b), min(r, g, b)
        return (mx - mn) / (mx + 1e-6)

    def is_bg(c):
        # 近白/近亮灰或近黑:大概率是参考图背景,不当主/辅色
        l, s = lum(c), sat(c)
        return (l > 235 and s < 0.15) or (l < 18 and s < 0.15)

    # 主/辅/点缀只从非背景色里选;全被滤掉(纯白图等)才回退全量
    cand = [c for c in colors if not is_bg(c)] or colors

    primary = cand[0]
    secondary = cand[1] if len(cand) > 1 else primary

    pool = [c for c in cand[2:] if c not in (primary, secondary)]
    accent = max(pool, key=sat) if pool else "#FFB4A2"

    # 眼白:优先取真正的高亮色,没有则默认白(卡通宠物眼白通常就是白)
    light = [c for c in colors if lum(c) > 140]
    eye = max(light, key=lum) if light else "#FFFFFF"

    # 描边/瞳孔:只从「暗且中低饱和」里选,避免把高饱和亮色误当暗色
    def is_dark(c):
        return lum(c) < 60 or (lum(c) < 120 and sat(c) < 0.5)

    dark = [c for c in colors if is_dark(c)]
    # 排除已被 accent 占用的,尽量让 6 个槽位不重复
    dark_no_acc = [c for c in dark if c != accent]
    line = min(dark_no_acc, key=lum) if dark_no_acc else "#2B2B2B"
    dark2 = [c for c in dark_no_acc if c != line]
    pupil = min(dark2, key=lum) if dark2 else "#1E1E1E"

    return {
        "--pet-primary": primary,
        "--pet-secondary": secondary,
        "--pet-accent": accent,
        "--pet-eye": eye,
        "--pet-pupil": pupil,
        "--pet-line": line,
    }