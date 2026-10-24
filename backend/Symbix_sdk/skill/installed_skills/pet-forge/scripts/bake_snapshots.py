"""Script A — 烘焙快照:把 SVG rig + states.json + keyframes.json 逐帧渲染成 PNG 序列。

用法:
    python bake_snapshots.py --rig assets/fixtures/base.svg --states /tmp/states.json \
        -n "Mochi" -o build/mochi [--keyframes config/keyframes.json] [--map config/spritesheet_map.json]

输出:
    build/{name}/{home_state}/frame_NN.png    每 Home 行(状态)一目录,帧从 0 起。

帧切换语义:
    - translate 类:部件整体位移(最安全,不破网格,位移取整像素)。
    - rotateZ(wave/sway):围绕部件 transform-origin 旋转,仅限肢体/尾巴。
    - frameSwap(blink/close/open-startled):闭眼 = 眼部件 scaleY 压扁(服务端图层切换)。
    - state 引用了 keyframes 没定义的动画 → 显式报错(契约断裂)。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import read_text  # noqa: E402
from render_pil import svg_to_png  # noqa: E402

_ANIM_RE = re.compile(r"^(?P<name>[a-z0-9-]+)\s+")
_EYE_CLOSED_SCALE_Y = 0.08

# 常见默认 transform-origin(与 rig-spec 建议一致)
_DEFAULT_ORIGIN = {
    "body": (100.0, 120.0),
    "eye-left": (80.0, 90.0), "eye-right": (120.0, 90.0),
    "pupil-left": (80.0, 90.0), "pupil-right": (120.0, 90.0),
    "mouth": (100.0, 130.0), "tail": (148.0, 130.0),
    "limb-left": (70.0, 150.0), "limb-right": (130.0, 150.0),
    "ear-left": (70.0, 70.0), "ear-right": (130.0, 70.0),
}

from pack_theme import inject_palette_to_svg, resolve_palette  # noqa: E402

# ---------- transform 注入 ----------


def prepare_svg(svg: str, palette: dict[str, str] | None = None) -> str:
    """烘焙前把主题色注入根 style。

    render_pil 只认根 style 的 --pet-*,rig 没声明 var(--pet-*) 就会整只落兜底黑
    (skill 自带的 fixture 就是这种情况)。所以渲染前必须先补齐调色板,
    保证「打包出的 base.svg」与「烘焙出的 spritesheet」用同一套颜色。
    """
    return inject_palette_to_svg(svg, resolve_palette(svg, palette))


def _set_transform(svg: str, part_id: str, transform: str) -> str:
    """给部件 <g> 追加 transform(与已有 transform **组合**,不再覆盖)。

    SVG 语义:transform 列表从左到右相乘,「已有」在前、「新增」在后 = 新增先作用于点,
    即「部件自身的变换保持不变,动画在它的局部坐标系里叠加」。
    旧实现是直接替换,于是 rig 自带的 transform 与「奔跑整身位移」都会被动画覆盖掉。
    同一帧重复注入同一变换时忽略(避免幂等性问题)。
    """
    pat = rf'(<g\b[^>]*\bid\s*=\s*["\']{re.escape(part_id)}["\'][^>]*>)'
    m = re.search(pat, svg)
    if not m:
        return svg
    tag = m.group(1)
    mt = re.search(r'transform\s*=\s*"([^"]*)"', tag)
    if mt:
        cur = mt.group(1).strip()
        if transform in cur:  # 同一帧重复注入同一条变换 → 不叠加
            return svg
        merged = f"{cur} {transform}" if cur else transform
        tag = tag[: mt.start()] + f'transform="{merged}"' + tag[mt.end():]
    else:
        tag = tag[:-1] + f' transform="{transform}">'
    return svg[: m.start()] + tag + svg[m.end():]


def _rig_parts(svg: str) -> list[str]:
    """按出现顺序列出 rig 的全部部件 id(<g id="…">)。"""
    return re.findall(r'<g\b[^>]*\bid\s*=\s*["\']([^"\']+)["\']', svg)


def _targets(preset: dict, part_ids: list[str], svg: str) -> list[str]:
    """决定一个动画作用到哪些部件。

    scope=rig  → rig 全部部件,用于 breathe / breathe-slow / bounce / lean-in 这类
                 「角色整体动」的动画。若只动 states 里写的那一个组,就会头动脸不动
                 (面部/耳朵留在原地 → 头身分离),这是最明显的崩坏来源。
    scope=part → states 里写明的部件;states 没写(直接调 inject_frame)时退回 preset.parts。
    """
    if str(preset.get("scope") or "part").lower() == "rig":
        return _rig_parts(svg)
    if part_ids:
        return list(part_ids)
    return list(preset.get("parts") or [])


def _transform_origin(svg: str, part_id: str) -> Optional[tuple[float, float]]:
    """从部件 g 的 transform-origin 提取中心点;缺失用默认表。"""
    m = re.search(
        rf'<g\b[^>]*\bid\s*=\s*["\']{re.escape(part_id)}["\'][^>]*?'
        r'transform-origin\s*[:=]\s*["\'(]?\s*([\d.]+)px?\s+([\d.]+)px?',
        svg,
    )
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return _DEFAULT_ORIGIN.get(part_id, (100.0, 120.0))# ---------- keyframes 采样 ----------

def _sample_value(segments: list[dict], t: float, key: str) -> float:
    """对 segments 线性插值采样 key 字段(t ∈ [0,1])。"""
    segs = sorted(segments, key=lambda s: s["t"])
    if not segs:
        return 0.0
    if t <= segs[0]["t"]:
        return segs[0].get(key, 0.0)
    if t >= segs[-1]["t"]:
        return segs[-1].get(key, 0.0)
    for i in range(len(segs) - 1):
        a, b = segs[i], segs[i + 1]
        if a["t"] <= t <= b["t"]:
            k = 0.0 if b["t"] == a["t"] else (t - a["t"]) / (b["t"] - a["t"])
            va, vb = a.get(key, 0.0), b.get(key, 0.0)
            return va + (vb - va) * k
    return 0.0


def _pixel(v: float) -> str:
    """translate 取整到像素网格(烘焙保证整数位移)。"""
    return str(int(round(v)))


# ---------- 帧采样 → 注入 SVG ----------

_SCALE_WARN = set()


def _warn(warnings: Optional[list[str]], message: str, *, echo: bool = False) -> None:
    """记录一条烘焙警告。

    有收集器就交给它(由 build_theme 写进 pet.json,前端/Agent 都能看到);
    没有收集器时退回 stderr,保证独立调用 bake_snapshots 也不静默。
    """
    if warnings is None:
        print(f"  [warn] {message}", file=sys.stderr)
        return
    if message not in warnings:
        warnings.append(message)
    if echo:
        print(f"  [warn] {message}")


def _note_targets(
    svg: str, anim: str, targets: list[str], warnings: Optional[list[str]]
) -> None:
    """动画目标部件不存在时记警告。

    _set_transform 找不到 id 会原样返回(降级:画面不崩,只是这个部件不动)。
    但「静默不动」是该修的错误 —— 必须让 Agent/用户看得见。
    """
    ids = set(_rig_parts(svg))
    if not targets:
        _warn(warnings, f"动画 {anim} 没有目标部件(states 与 keyframes 都没给出部件)")
        return
    missing = [p for p in targets if p not in ids]
    if missing:
        _warn(warnings, f"动画 {anim} 的目标部件不存在,已跳过: {missing}")


def inject_frame(svg: str, anim: str, t: float, part_ids: list[str],
                 keyframes: dict, *, amplitude: float = 1.0,
                 warnings: Optional[list[str]] = None) -> str:
    """把某动画在 t 时刻的变换注入 svg 的对应部件,返回新 SVG。

    anim 不在 keyframes → raise KeyError(契约断裂,显式失败而非静默跳过)。
    warnings: 可选收集器,记录「目标部件不存在」这类降级事件。
    """
    preset = keyframes.get("presets", {}).get(anim)
    if not preset:
        raise KeyError(
            f"keyframes 缺少动画 {anim!r}(states 应只引用 keyframes 定义的动画)"
        )
    kind = preset.get("kind")
    segs = preset.get("segments") or []
    out = svg

    if kind == "translateY":
        v = _sample_value(segs, t, "dy") * amplitude
        tr = f"translate(0 {_pixel(v)})"
        targets = _targets(preset, part_ids, out)
        _note_targets(out, anim, targets, warnings)
        for pid in targets:
            out = _set_transform(out, pid, tr)
    elif kind == "translateX":
        v = _sample_value(segs, t, "dx") * amplitude
        tr = f"translate({_pixel(v)} 0)"
        targets = _targets(preset, part_ids, out)
        _note_targets(out, anim, targets, warnings)
        for pid in targets:
            out = _set_transform(out, pid, tr)
    elif kind == "rotateZ":
        deg = _sample_value(segs, t, "deg") * amplitude
        targets = _targets(preset, part_ids, out)
        _note_targets(out, anim, targets, warnings)
        for pid in targets:
            ori = _transform_origin(out, pid)
            tr = f"rotate({round(deg, 2)} {_pixel(ori[0])} {_pixel(ori[1])})"
            out = _set_transform(out, pid, tr)
    elif kind == "frameSwap":
        swap = _sample_value(segs, t, "swap") >= 0.5
        if swap:
            _note_targets(out, anim, list(part_ids), warnings)
            for pid in part_ids:
                if "eye" in pid or "pupil" in pid:
                    ori = _transform_origin(out, pid)
                    tr = (
                        f"translate({_pixel(ori[0])} {_pixel(ori[1])}) "
                        f"scale(1 {_EYE_CLOSED_SCALE_Y}) "
                        f"translate({_pixel(-ori[0])} {_pixel(-ori[1])})"
                    )
                    out = _set_transform(out, pid, tr)
        # swap=false(睁眼):identity,不动
    else:
        raise KeyError(f"keyframes 动画 {anim!r} 的 kind 不支持: {kind!r}")
    return out# ---------- 行映射烘焙 ----------

def _mirror_wrap(svg: str) -> str:
    """整 SVG 内容包一层 scale(-1 1)(水平镜像,用于 runningLeft)。

    平移量必须用画板宽度(不是写死的 200):画板 192×208 时写 200 会把整只宠物
    右移 8 格并在右边被裁掉。
    """
    m_open = re.search(r"<svg\b[^>]*>", svg)
    if not m_open:
        return svg
    inner_open = m_open.end()
    inner_close = svg.rfind("</svg>")
    if inner_close <= inner_open:
        return svg
    vb = re.search(r'viewBox="\s*([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)', svg[:inner_open])
    width = float(vb.group(3)) if vb else 200.0
    width_s = f"{width:g}"
    inner = svg[inner_open:inner_close]
    wrapped = f'<g transform="translate({width_s} 0) scale(-1 1)">' + inner + "</g>"
    return svg[:inner_open] + wrapped + svg[inner_close:]


def _swap_spans(segments: list[dict]) -> list[tuple[float, float]]:
    """把 frameSwap 的 segments 推成 swap=true 的 t 区间列表(密集采样法,不用解析)。"""
    spans: list[tuple[float, float]] = []
    lo: Optional[float] = None
    for i in range(101):
        t = i / 100.0
        on = _sample_value(segments, t, "swap") >= 0.5
        if on and lo is None:
            lo = t
        elif not on and lo is not None:
            spans.append((lo, max(0.0, (i - 1) / 100.0)))
            lo = None
    if lo is not None:
        spans.append((lo, 1.0))
    return spans


def _event_plan(
    anim_rules: list[tuple[str, list[str]]], keyframes: dict, ts: list[float]
) -> dict[str, dict[int, float]]:
    """为「必须被采到」的事件类动画(preset.must_hit)安排一帧强制命中。

    时间曲线按帧数均匀采样时,窄窗口常被整段跳过 —— 例如 blink 只占 t∈[0.5,0.6),
    而 idle 行只有6帧(t=0/0.2/0.4/0.6/0.8/1.0),于是一只都不眨眼。
    这里在「一帧都没采到」时,把最接近窗口中点的那一帧的这个动画的时刻改成窗口中点;
    只影响这一条动画,不牵动同帧其它部件。
    """
    plan: dict[str, dict[int, float]] = {}
    for name, _parts in anim_rules:
        preset = (keyframes.get("presets") or {}).get(name) or {}
        if preset.get("kind") != "frameSwap" or not preset.get("must_hit"):
            continue
        spans = _swap_spans(preset.get("segments") or [])
        if not spans or any(lo <= t <= hi for t in ts for lo, hi in spans):
            continue
        mid = (spans[0][0] + spans[0][1]) / 2.0
        best = min(range(len(ts)), key=lambda i: abs(ts[i] - mid))
        plan.setdefault(name, {})[best] = mid
    return plan


def bake_row(
    svg_base: str,
    states: dict,
    row_cfg: dict,
    variants: dict,
    keyframes: dict,
    out_dir: Path,
    *,
    render_scale: int,
    nearest: bool,
    pixel: bool = False,
    raster_post: bool = False,
    palette: dict[str, str] | None = None,
    warnings: Optional[list[str]] = None,
) -> list[str]:
    """烘焙一行(spritesheet 的一行 = 一个 home 状态)。返回渲染成功的帧路径。

    raster_post=True:镜像与水平滚动不在 SVG 层做,交给调用方在渲染出的 PNG 上处理。
    SVG 层的 scale(-1 1) 与「覆盖部件 transform」在部分 rig/渲染器上会得到空白帧或
    丢掉滚动(部件自带动画会把 transform 覆盖回去),位图后处理更稳。
    """
    home = row_cfg["home"]
    source = row_cfg.get("source") or "idle"
    mode = row_cfg.get("mode") or "direct"
    var = variants.get(home, {})
    n_frames = int(row_cfg.get("frames") or 6)
    svg_base = prepare_svg(svg_base, palette)

    # 镜像只认 variants.mirror(runningLeft:true → 朝左;runningRight 不镜像 → 朝右)。
    # 旧写法 "mirror" in mode 会把 runningRight 也镜像,两行长得一模一样;既然
    # mode 名里 runningLeft 带 mirror-back,变体缺失时才退回按 home 判断。
    mirror_flag = var.get("mirror")
    use_mirror = bool(mirror_flag) if mirror_flag is not None else home == "runningLeft"

    # 取源状态的动画规则
    rules = states.get(source) or {}
    anim_rules = []
    for key, decl in (rules or {}).items():
        m = _ANIM_RE.match(str(decl).strip())
        name = m.group(1).lower() if m else None
        if not name:
            continue
        part_ids = [p.strip() for p in str(key).split(",") if p.strip()]
        anim_rules.append((name, part_ids))

    # 模式修饰
    amplitude = float(var.get("amplitude_factor", 1.0)) if mode == "amplify-bounce" else 1.0
    scroll_dx = float(var.get("scroll_dx", 0.0) or 0.0)
    # cycle:把行内帧映射到 cycles 个虚拟循环的相位上,让与同一 source 的另一行观感不同
    # (例:running(思考中) 与 waiting(等待) 同用 listening,不区分就长得一模一样)。
    cycles = max(1, int(var.get("cycles") or 2)) if mode == "cycle" else 1

    def _t_of(f: int) -> float:
        # review:取 sleeping 前 head_frames 帧,其余帧复用最后一帧
        cur = min(f, int(var.get("head_frames", 4)) - 1) if mode == "head-frames" else f
        t = cur / max(n_frames - 1, 1)
        return (t * cycles) % 1.0 if cycles > 1 else t

    ts = [_t_of(f) for f in range(n_frames)]
    # 必须被采到的事件类动画(眨眼等):均匀采样常整段跳过窄窗口,这里补一帧强制命中
    event_plan = _event_plan(anim_rules, keyframes, ts)

    row_out = out_dir / home
    Path(row_out).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for f in range(n_frames):
        t = ts[f]

        frame_svg = svg_base
        if use_mirror and not raster_post:
            frame_svg = _mirror_wrap(frame_svg)

        # 奔跑:整身水平往复位移(±scroll_dx/2);raster_post 时改在 PNG 上平移
        if scroll_dx and not raster_post:
            dx = math.sin(t * math.tau) * scroll_dx * 0.5
            frame_svg = _set_transform(frame_svg, "body",
                                       f"translate({_pixel(dx)} 0)")

        # 逐部件注入动画变换
        for name, part_ids in anim_rules:
            tt = event_plan.get(name, {}).get(f, t)
            frame_svg = inject_frame(frame_svg, name, tt, part_ids,
                                     keyframes, amplitude=amplitude,
                                     warnings=warnings)

        out_png = row_out / f"frame_{f:02d}.png"
        data = svg_to_png(
            frame_svg, str(out_png),
            width=192, height=208, scale=render_scale,
            background=None,  # 透明
            resample=0 if nearest else 1,  # NEAREST / LANCZOS
            pixel=pixel,  # 像素画板模式(200x200 格 → 整数栅格化 → 调色板量化)
        )
        if data is None:
            _warn(warnings, f"渲染失败: {home}/frame_{f:02d}", echo=True)
            continue
        paths.append(str(out_png))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="烘焙 pet-forge 主题为帧 PNG 序列")
    ap.add_argument("--rig", required=True, help="base.svg 路径")
    ap.add_argument("--states", required=True, help="states.json 路径")
    ap.add_argument("-n", "--name", default="pet", help="输出 pet 名(目录名)")
    ap.add_argument("-o", "--out", default="build", help="输出根目录")
    ap.add_argument("--keyframes", default=None, help="keyframes.json(默认 config/keyframes.json)")
    ap.add_argument("--map", default=None, help="spritesheet_map.json(默认 config/spritesheet_map.json)")
    ap.add_argument("--scale", type=int, default=2, help="渲染超采样倍数(默认 2 = 抗锯齿;像素风用 1 配 --nearest)")
    ap.add_argument("--nearest", action="store_true", help="NEAREST 降采样(保硬边)")
    ap.add_argument("--pixel", action="store_true",
                    help="像素画板模式:viewBox 当画板按整数格栅格化 + 调色板量化(忽略 --scale/--nearest)")
    args = ap.parse_args()

    cfg = Path(__file__).resolve().parent.parent / "config"
    kf_path = Path(args.keyframes) if args.keyframes else cfg / "keyframes.json"
    map_path = Path(args.map) if args.map else cfg / "spritesheet_map.json"

    svg = read_text(args.rig)
    states = json.loads(read_text(args.states))
    keyframes = json.loads(read_text(kf_path))
    mapping = json.loads(read_text(map_path))
    variants = mapping.get("variants", {})
    out_root = Path(args.out) / args.name

    warnings: list[str] = []
    total, ok = 0, 0
    for row in mapping.get("rows", []):
        paths = bake_row(
            svg, states, row, variants, keyframes, out_root,
            render_scale=args.scale, nearest=args.nearest, pixel=args.pixel,
            warnings=warnings,
        )
        total += int(row.get("frames") or 6)
        ok += len(paths)
        print(f"  [{row['home']:<12}] {len(paths)}/{row.get('frames') or 6} 帧")
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    print(f"完成: {ok}/{total} 帧 → {out_root}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())