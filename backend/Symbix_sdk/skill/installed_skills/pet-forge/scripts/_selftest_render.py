"""渲染级回归自测:把「校验全过、画面是坏的」变成红灯。

背景:validate_rig / validate_states 只查结构契约,而烘焙链路的缺陷全都静默通过。
本文件按已知缺陷逐条断言,修好前应当全红(先红后绿)。

覆盖:
  C  render_pil 的变换链顺序与 SVG 语义相反(translate+scale / 嵌套 g)
  A  全身类位移只作用于 states 里写的那一个组(parts_origin 未生效 → 面部不跟随)
  B  rotateZ 用 preset.parts 覆盖 states 部件(耳朵规则去转尾巴 / 死动画)
  D  时间曲线按帧数均匀采样 → 闭眼窗口(window 太小)采不到
  E  192x208 与 viewBox 200x200 不等比(像素风被压扁 + 亚像素台阶)
  F  静默失败:未解析的 var() 落兜底黑、spritesheet_map 的 mode 无实现、同一 source 两行逐帧相同
  F  契约无人校验:preset 指向 rig 不存在的部件 / states 引用了未定义的动画
  G  path 的绝对坐标(M/L/H/V)曾写反:绝对分支丢掉 x、y 累加 → 每个 <path> 都从画布
     原点拉出一条斜边,AI 生成的图形(几乎全是 path)被糊成一团

用法:
    python scripts/_selftest_render.py [--rig X.svg] [--states Y.json]
退出码 0 = 全绿;1 = 有红灯。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:  # Windows 控制台默认 GBK,中文报错会崩
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from PIL import Image  # noqa: E402

from _common import read_text  # noqa: E402
from _common import VIEWBOX_CANVAS, VIEWBOX_LEGACY  # noqa: E402
from bake_snapshots import bake_row, inject_frame, prepare_svg  # noqa: E402
from render_pil import parse_color, svg_to_png  # noqa: E402
from validate_states import validate_states  # noqa: E402

ROOT = _SCRIPTS.parent
FIX = ROOT / "assets" / "fixtures"
CONFIG = ROOT / "config"

# 渲染尺寸以 spritesheet_map 为准(Home.vue 契约)
FRAME_W, FRAME_H = 192, 208
# 测试用调色板:每个变量取值互不相同,便于按颜色定位部件
TEST_PALETTE = {
    "--pet-primary": "#F7F2EA",
    "--pet-secondary": "#F3C1CE",
    "--pet-accent": "#E25555",
    "--pet-eye": "#FFFFFF",
    "--pet-pupil": "#3F8FD2",
    "--pet-line": "#3A3540",
}
EYE_PARTS = ["eye-left", "eye-right", "pupil-left", "pupil-right"]
# bake_row 真正实现了的 mode(其余 mode 只是装饰性字符串,靠 variants 开关兜)
HANDLED_MODES = {"direct", "amplify-bounce", "head-frames", "cycle",
                 "mirror+scroll-x", "mirror-back+scroll-x"}

_RESULT: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _RESULT.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


# ── 渲染工具 ──────────────────────────────────────────────────
def ensure_palette(svg: str, palette: dict[str, str]) -> str:
    """把调色板写进根节点 style(渲染器只认根 style 里的 --pet-*)。"""
    if "--pet-" in svg[: svg.find(">") + 1] and "style=" in svg[: svg.find(">") + 1]:
        return svg
    decl = ";".join(f"{k}:{v}" for k, v in palette.items())
    return svg.replace("<svg", f'<svg style="{decl}"', 1)


def render(svg: str, w: int = FRAME_W, h: int = FRAME_H) -> Image.Image:
    data = svg_to_png(svg, width=w, height=h, scale=1, resample=0)
    assert data, "渲染失败(返回 None)"
    return Image.open(io.BytesIO(data)).convert("RGBA")


def color_pixels(im: Image.Image, color: tuple[int, int, int]) -> list[tuple[int, int]]:
    w = im.size[0]
    return [(i % w, i // w) for i, p in enumerate(im.get_flattened_data())
            if p[3] > 0 and p[:3] == color]


def hex_rgb(v: str) -> tuple[int, int, int]:
    c = parse_color(v)
    assert c, v
    return (c[0], c[1], c[2])


def parts_with_transform(svg: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r'<g\b[^>]*\bid="([^"]+)"[^>]*\btransform="([^"]*)"', svg)}


def sample_value(segments: list[dict], t: float, key: str) -> float:
    """与 bake_snapshots._sample_value 同语义的线性采样(此处独立实现,避免耦合)。"""
    segs = sorted(segments, key=lambda s: s["t"])
    if t <= segs[0]["t"]:
        return segs[0].get(key, 0.0)
    if t >= segs[-1]["t"]:
        return segs[-1].get(key, 0.0)
    for a, b in zip(segs, segs[1:]):
        if a["t"] <= t <= b["t"]:
            k = 0.0 if b["t"] == a["t"] else (t - a["t"]) / (b["t"] - a["t"])
            return a.get(key, 0.0) + (b.get(key, 0.0) - a.get(key, 0.0)) * k
    return 0.0


# ── 断言 ──────────────────────────────────────────────────────
def check_c_matrix() -> None:
    """C:translate+scale 链 —— 镜像包装必须可见,且内容真的翻到右边。"""
    syn = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
           '<g transform="translate(200 0) scale(-1 1)">'
           '<rect x="10" y="10" width="20" height="20" fill="#000000"/></g></svg>')
    im = render(syn, 200, 200)
    pts = color_pixels(im, (0, 0, 0))
    xs = [x for x, _ in pts]
    check(
        "R1 [C] 镜像包装 translate+scale 渲染可见且翻到右侧",
        bool(pts) and min(xs) >= 160,
        f"墨迹像素={len(pts)} x范围={(min(xs), max(xs)) if xs else '无'} 期望 170~190",
    )


def check_c_frameswap(rig: str, kf: dict) -> None:
    """C:闭眼必须是「压扁」,不是「眼睛飞出画布」。"""
    pupil = hex_rgb(TEST_PALETTE["--pet-pupil"])
    base = render(rig)
    n0 = len(color_pixels(base, pupil))
    closed = inject_frame(rig, "close", 0.9, EYE_PARTS, kf)
    n1 = len(color_pixels(render(closed), pupil))
    check(
        "R2 [C] 闭眼帧瞳孔像素「减少但 >0」(压扁而非消失)",
        0 < n1 < n0,
        f"瞳孔像素 {n0} → {n1}",
    )


def check_a_scope(rig: str, kf: dict) -> None:
    """A:states 里 body 类位移应带动整个角色(面部跟随),否则脸与头分离。"""
    pupil = hex_rgb(TEST_PALETTE["--pet-pupil"])
    base = render(rig)
    ys0 = [y for _, y in color_pixels(base, pupil)]
    bounced = inject_frame(rig, "bounce", 0.4, ["body"], kf)
    ys1 = [y for _, y in color_pixels(render(bounced), pupil)]
    if not ys0 or not ys1:
        check("R3 [A] 全身位移带动面部", False, "瞳孔像素丢失,无法判定")
        return
    dy = sum(ys1) / len(ys1) - sum(ys0) / len(ys0)
    check(
        "R3 [A] body 类位移(bounce dy=-12)应带动面部",
        dy <= -8,
        f"瞳孔 y 位移={dy:+.1f}px(期望 ≤ -8;≈0 表示面部没跟随)",
    )


def check_b_part_scope(rig: str, kf: dict) -> None:
    """B:rotateZ 必须听 states 指定的部件,preset.parts 只能当兜底。"""
    got = parts_with_transform(inject_frame(rig, "sway-slow", 0.25, ["ear-right"], kf))
    check(
        "R4a [B] rotateZ 听从 states 的部件(ear-right: sway-slow)",
        set(got) == {"ear-right"},
        f"实际带动={sorted(got) or '无'}",
    )
    got2 = parts_with_transform(inject_frame(rig, "wave", 0.25, ["tail"], kf))
    check(
        "R4b [B] 无 limb/accessory 的 rig 上 wave 仍应作用到 states 部件(tail)",
        "tail" in got2,
        f"实际带动={sorted(got2) or '无(preset.parts=limb-right/accessory 不存在 → 死动画)'}",
    )


def check_d_sampling(rig: str, states: dict, mapping: dict, kf: dict) -> None:
    """D:帧采样必须真的采到「闭眼/睁眼」这类窄窗口事件。

    不断言采样公式,只断言结果:带 must_hit 的帧动画在其所在行里,
    必须有一帧真的把瞳孔压扁(而不是整行都不眨眼)。
    """
    import tempfile

    presets = kf.get("presets", {})
    rows = {str(r.get("home")): r for r in mapping.get("rows", [])}
    variants = mapping.get("variants") or {}
    need: list[str] = []
    for row in mapping.get("rows", []):
        for decl in (states.get(row.get("source") or "idle") or {}).values():
            m = re.match(r"^([a-z0-9-]+)\s+", str(decl).strip())
            if not m:
                continue
            preset = presets.get(m.group(1).lower()) or {}
            if preset.get("kind") == "frameSwap" and preset.get("must_hit"):
                need.append(str(row.get("home")))
                break
    pupil = tuple(parse_color(TEST_PALETTE["--pet-pupil"])[:3])
    missing: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pf_d_selftest_") as tmp:
        for home in sorted(set(need)):
            paths = bake_row(rig, states, rows[home], variants, kf, Path(tmp),
                             render_scale=1, nearest=True, palette=TEST_PALETTE)
            counts = [len(color_pixels(Image.open(p).convert("RGBA"), pupil)) for p in paths]
            mx = max(counts) if counts else 0
            # 闭眼 = 瞳孔被压扁成一条(像素数显著低于本行最大值),但不得归零(归零=飞出画布)
            if not any(0 < c <= mx * 0.75 for c in counts):
                missing.append(f"{home}: 瞳孔像素/帧={counts}")
    check(
        "R5 [D] 带 must_hit 的帧动画在对应行必须真的出现一次",
        not missing,
        "; ".join(missing) or f"已覆盖行={sorted(set(need))}(闭眼帧瞳孔像素 ≪ 其它帧)",
    )


def check_g_path_geometry() -> None:
    """G:path 的绝对坐标必须生效 —— 只按结果断言:墨迹要落在 d 写的位置上。

    曾经的 bug:绝对分支写成 `x + (t if rel else 0)`,L/M 的绝对坐标全被丢掉
    (x 恒为上一个点、y 累加)→ 每个 path 都额外多出一条从画布原点 (0,0) 拉到
    起点的斜边,而真正要画的多边形退化成一条贴在 x=0 上的竖线。
    这里用一个远离原点的三角形/折线来钉住:修好前墨迹会全部堆在 x≈0。
    """

    def ink_bbox(d: str, attrs: str) -> tuple[int, int, int, int] | None:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
               f'<path d="{d}" {attrs}/></svg>')
        pts = color_pixels(render(svg, 200, 200), (0, 0, 0))
        if not pts:
            return None
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    fill = 'fill="#000000"'
    stroke = 'fill="none" stroke="#000000" stroke-width="1"'
    cases = [
        ("L 绝对多边形", "M150 150 L190 150 L190 190 L150 190 Z", fill, (150, 150, 189, 189)),
        ("M/L 绝对折线", "M20 20 L40 20", stroke, (19, 19, 40, 20)),
        ("H/V 绝对", "M150 20 H190 V60 H150 Z", fill, (150, 20, 189, 59)),
        ("相对 m/l", "m150 150 l40 0 l0 40 l-40 0 z", fill, (150, 150, 189, 189)),
        ("多子路径 M…M…", "M20 20 L30 20 M150 150 L160 150", stroke, (19, 19, 160, 150)),
    ]
    for label, d, attrs, want in cases:
        box = ink_bbox(d, attrs)
        ok = box is not None and all(abs(a - b) <= 4 for a, b in zip(box, want))
        check(f"R10 [G] {label} 渲染落在 d 指定的位置", ok, f"墨迹 bbox={box} 期望≈{want}")

    # 远离原点的图形绝不能出现原点附近的墨迹(origin 斜边就是这个 bug 的指纹)
    box = ink_bbox("M150 150 L190 150 L190 190 L150 190 Z", fill)
    check(
        "R10b [G] 远离画布原点的 path 不得在左上角留下墨迹",
        box is not None and box[0] >= 140 and box[1] >= 140,
        f"墨迹 bbox={box}(期望左上角 ≥ (140,140);出现 x≈0 即绝对坐标被丢掉)",
    )


def check_e_aspect(rig_raw: str) -> None:
    """E:渲染必须等比 —— viewBox 里的正方形在帧里仍是正方形(居中,不拉伸)。"""
    sq = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        '<rect x="50" y="50" width="100" height="100" fill="#000000"/></svg>'
    )
    im = render(sq, w=FRAME_W, h=FRAME_H)
    pts = color_pixels(im, (0, 0, 0))
    if not pts:
        check("R6 [E] 等比渲染(viewBox 正方形 → 帧内仍是正方形)", False, "没渲染出任何像素")
        return
    w = max(x for x, _ in pts) - min(x for x, _ in pts) + 1
    h = max(y for _, y in pts) - min(y for _, y in pts) + 1
    check(
        "R6 [E] 等比渲染(viewBox 正方形 → 帧内仍是正方形)",
        abs(w - h) <= 1 and 90 <= w <= 100,
        f"墨迹 {w}x{h}px(100x100 方块 + 200x200 viewBox → 期望 ~96x96;拉长会变成 96x104)",
    )


def check_f_silent(rig_raw: str, mapping: dict) -> None:
    """F:静默失败 —— 未解析的 var() 落兜底黑需在烘焙入口被补齐、mode 都要有实现。"""
    prepared = render(prepare_svg(rig_raw))
    n_black = len(color_pixels(prepared, (0, 0, 0)))
    n_ink = sum(1 for p in prepared.get_flattened_data() if p[3] > 0)
    check(
        "R7 [F] 经烘焙入口(prepare_svg)渲染不应落兜底黑",
        n_black == 0 and n_ink > 0,
        f"兜底黑像素={n_black}/{n_ink}(rig 未声明 --pet-* 时必须由调色板补齐)",
    )

    # 直接渲染未注入的 rig 时必须「响亮地」告警,而不是静默变黑
    buf = io.StringIO()
    old_err = sys.stderr
    sys.stderr = buf
    try:
        render(rig_raw)
    finally:
        sys.stderr = old_err
    check(
        "R7b [F] 未解析 var() 必须告警(不得静默变黑)",
        "颜色变量未解析" in buf.getvalue(),
        f"stderr={buf.getvalue().strip()[:80] or '无输出'}",
    )

    used = {str(r.get("mode")) for r in mapping.get("rows", [])}
    bad = sorted(used - HANDLED_MODES)
    check(
        "R8a [F] spritesheet_map 的 mode 都有实现(不能只是装饰字符串)",
        not bad,
        f"无实现的 mode={bad}",
    )


def check_f_rows_differ(rig: str, states: dict, mapping: dict, kf: dict) -> None:
    """F:不同 home 行必须真的长得不一样(同 source 的两行曾经逐帧完全相同)。"""
    import tempfile

    rows = {r["home"]: r for r in mapping.get("rows", [])}
    variants = mapping.get("variants") or {}
    same_source: dict[str, list[str]] = {}
    for r in mapping.get("rows", []):
        same_source.setdefault(str(r.get("source")), []).append(r["home"])
    pairs = [(v[0], v[1]) for v in same_source.values() if len(v) > 1]
    with tempfile.TemporaryDirectory(prefix="pf_rend_selftest_") as tmp:
        sig: dict[str, list[bytes]] = {}
        for a, b in pairs:
            for home in (a, b):
                if home in sig:
                    continue
                paths = bake_row(rig, states, rows[home], variants, kf, Path(tmp),
                                 render_scale=1, nearest=True, palette=TEST_PALETTE)
                sig[home] = [Image.open(p).convert("RGBA").tobytes() for p in paths]
    dup = [f"{a}≡{b}" for a, b in pairs if sig.get(a) == sig.get(b)]
    check(
        "R8b [F] 同一 source 的不同 home 行不得逐帧完全相同",
        not dup,
        "重复行=" + (", ".join(dup) or "无") + f"(检查对={pairs})",
    )


def check_f_contract(rig: str, states: dict, kf: dict) -> None:
    """F:keyframes 契约必须可校验(preset.parts ⊆ rig、动画名有定义)。"""
    part_ids = re.findall(r'<g\b[^>]*\bid="([^"]+)"', rig)
    try:
        ok_errs = validate_states(states, part_ids=part_ids, keyframes=kf, check_mirrors=False)
        bad_kf = {"presets": {"ghost": {"kind": "rotateZ", "parts": ["limb-right"],
                                     "segments": [{"t": 0, "deg": 0}]}}}
        bad_errs = validate_states(
            {"idle": {"tail": "ghost 1s ease 1"}}, part_ids=part_ids, keyframes=bad_kf,
            require_all_states=False, check_mirrors=False,
        )
        rules = {e.get("rule") for e in bad_errs}
    except TypeError as e:
        check("R9 [F] validate_states 应支持 keyframes 契约校验", False, f"接口尚不支持:{e}")
        return
    check(
        "R9 [F] validate_states(keyframes=) 应校验 preset.parts ⊆ rig",
        (not ok_errs) and {"preset_unknown_part"} <= rules,
        f"正常契约报错={len(ok_errs)} 条(期望 0);恶意契约规则={sorted(rules)}",
    )


def check_pixel_style() -> None:
    """R11 [像素风] 像素画板契约:整数格栅格化 + 调色板量化 + 真硬边。

    背景:像素风原来只是提示词里一句话,烘焙默认 --scale 2 抗锯齿,
    于是 AI 交上来的「像素画」其实是插值糊图。本组断言只看渲染结果。
    """
    rig_path = FIX / "pixel-base.svg"
    if not rig_path.is_file():
        check("R11 像素模板 rig 存在", False, f"缺文件 {rig_path}")
        return
    rig = ensure_palette(read_text(rig_path), TEST_PALETTE)
    px = svg_to_png(rig, width=FRAME_W, height=FRAME_H, pixel=True)
    if px is None:
        check("R11 支持像素模式渲染(svg_to_png pixel=True)", False, "渲染返回 None")
        return
    im = Image.open(io.BytesIO(px)).convert("RGBA")
    colors = {}
    for p in im.getdata():
        if p[3]:
            colors[p] = colors.get(p, 0) + 1

    check("R11a 像素渲染不得出现半透明像素(无抗锯齿)",
          not any(0 < c[3] < 255 for c in colors),
          f"半透明色={sum(n for c, n in colors.items() if 0 < c[3] < 255)}px")
    pal_hex = re.findall(r"--pet-[a-z-]+\s*:\s*(#[0-9A-Fa-f]{6})", rig)
    pal = {tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in pal_hex}
    stray = {c[:3] for c in colors} - pal
    check("R11b 像素渲染颜色必须吸附到主题调色板",
          not stray and pal, f"越界色={sorted(stray)[:5]} 实收色数={len(colors)}")

    same = all(svg_to_png(rig, width=FRAME_W, height=FRAME_H, pixel=True, scale=s, resample=r) == px
               for s, r in ((1, 0), (2, 3)))
    check("R11c 像素模式下 scale/resample 不得影响结果", same)

    # 整数格:用一块纯矩形(40..160 格)验「1 格 = 1 像素」的硬边与精确落格
    def grid_edges(viewbox: str) -> tuple[set, set, int]:
        grid_rig = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
                    'style="--pet-primary:#7C9EFF"><g id="body" transform-origin="100px 100px">'
                    '<rect x="40" y="40" width="120" height="120" fill="var(--pet-primary)"/></g></svg>')
        gim = Image.open(io.BytesIO(svg_to_png(grid_rig, width=FRAME_W, height=FRAME_H, pixel=True))).convert("RGBA")
        body = (124, 158, 255)
        tops, bots, width = set(), set(), 0
        for x in range(FRAME_W):
            ys = [y for y in range(FRAME_H) if gim.getpixel((x, y))[:3] == body]
            if ys:
                tops.add(min(ys))
                bots.add(max(ys))
                width += 1
        return tops, bots, width

    tops, bots, width = grid_edges(VIEWBOX_CANVAS)
    # 格语义 = 「坐标是格索引,首末格都填」:x=40 w=120 占 40..160 共 121 格(与 path/polygon 一致)
    check("R11d 画板 = 帧尺寸时整数格 1:1 精确落格(边缘平直无锯齿)",
          len(tops) == 1 and len(bots) == 1 and width == 121 and sorted(tops) == [40] and sorted(bots) == [160],
          f"上边缘={sorted(tops)} 下边缘={sorted(bots)} 宽={width}px(期望 40/160/121)")

    tops, bots, width = grid_edges(VIEWBOX_LEGACY)
    check("R11d2 老画板 200x200 仍可用(0.96 等比缩放进帧,边缘仍平直)",
          len(tops) == 1 and len(bots) == 1 and abs(width - 115) <= 3,
          f"上边缘={sorted(tops)} 下边缘={sorted(bots)} 宽={width}px(期望 ≈115)")

    smooth = Image.open(io.BytesIO(svg_to_png(rig, width=FRAME_W, height=FRAME_H))).convert("RGBA")
    n_smooth = len({p for p in smooth.getdata() if p[3]})
    check("R11e 同一 rig 平滑模式仍抗锯齿(颜色数远多于像素模式)",
          n_smooth > len(colors) * 3, f"smooth={n_smooth} pixel={len(colors)}")

    vb = (re.search(r'viewBox="([^"]+)"', rig) or [None, ""])[1]
    check("R11f 随包像素模板的画板 = 帧尺寸(1 格 = 1 像素,零重采样)",
          " ".join(vb.split()) == VIEWBOX_CANVAS and im.size == (FRAME_W, FRAME_H),
          f'viewBox={vb!r} 尺寸={im.size}')



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pet-forge 渲染级回归自测")
    ap.add_argument("--rig", default=str(FIX / "base.svg"))
    ap.add_argument("--states", default=str(FIX / "states.json"))
    args = ap.parse_args(argv)

    rig_raw = read_text(args.rig)
    states = json.loads(read_text(args.states))
    mapping = json.loads(read_text(CONFIG / "spritesheet_map.json"))
    kf = json.loads(read_text(CONFIG / "keyframes.json"))
    rig = ensure_palette(rig_raw, TEST_PALETTE)

    print(f"[rig]    {args.rig}")
    print(f"[states] {args.states}")
    print("\n=== 渲染级断言(修复前应全红)===")
    check_c_matrix()
    check_g_path_geometry()
    check_c_frameswap(rig, kf)
    check_a_scope(rig, kf)
    check_b_part_scope(rig, kf)
    check_d_sampling(rig, states, mapping, kf)
    check_e_aspect(rig_raw)
    check_f_silent(rig_raw, mapping)
    check_f_rows_differ(rig, states, mapping, kf)
    check_f_contract(rig, states, kf)
    check_pixel_style()

    failed = [n for n, ok, _ in _RESULT if not ok]
    print(f"\n=== {len(_RESULT) - len(failed)} PASS / {len(failed)} FAIL ===")
    for n in failed:
        print(f"  - {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
