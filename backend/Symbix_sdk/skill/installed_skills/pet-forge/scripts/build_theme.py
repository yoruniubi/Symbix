"""一键构建 pet-forge 主题:校验 → 烘焙帧 → 拼 spritesheet → 写 pet.json。

用法:
    python build_theme.py --name "小白兔" --rig base.svg --states states.json
        [--out DIR] [--description "..."] [--palette '{"--pet-primary":"#fff"}']
        [--no-bake] [--keep-frames] [--scale N] [--nearest] [--template-fallback]

为什么需要它:
    base.svg + states.json 只是「矢量源文件」,而 Home.vue 只认 8×9 spritesheet。
    只跑 pack_theme 会留下一个「皮肤窗口看不到、切换后没效果」的半成品,
    所以这里把 validate → bake → pack → pet.json 串成一步,Agent 只需跑一条命令。

输出目录默认按仓库结构推导(不写死盘符):
    <项目根>/Symbix_frontend/public/pixiv_pet/<name>
    可用 --out 或环境变量 SYMBIX_PIXIV_PET_DIR 覆盖。

产物:
    <out>/base.svg + states.json + theme.json   rig 源文件(可再次修缮/重新烘焙)
    <out>/spritesheet.png + spritesheet.webp     Home.vue 契约帧动画
    <out>/pet.json                               Codex 桌宠元数据(与 codex_pet 兼容)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import list_part_ids_from_svg, read_text, write_json  # noqa: E402
from bake_snapshots import bake_row  # noqa: E402
from derive_mirrors import derive_mirrors  # noqa: E402
from pack_spritesheet import COLS, FRAME_H, FRAME_W, pack_frames  # noqa: E402
from pack_theme import pack_theme, palette_from_svg  # noqa: E402
from validate_rig import split_levels, validate_rig  # noqa: E402
from validate_states import validate_states  # noqa: E402

_CONFIG_DIR = _SCRIPTS.parent / "config"
# 兑底模板:AI 真的产出不了合法 rig 时,用这两个已知合法的部件图先行打包,
# 保证「永远有一个能动、可切换的宠物」(丑但可用 > 什么都装不上)。
_TEMPLATE_RIG = _SCRIPTS.parent / "assets" / "fixtures" / "base.svg"
# 像素风的兜底模板(整数格 + 只走直线),与像素契约一致
_TEMPLATE_RIG_PIXEL = _SCRIPTS.parent / "assets" / "fixtures" / "pixel-base.svg"
_TEMPLATE_STATES = _SCRIPTS.parent / "assets" / "fixtures" / "states.json"


def _add_warning(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def default_public_dir() -> Path:
    """前端静态资源目录 public/(项目根可由脚本位置推出,避免写死绝对路径)。"""
    env = os.environ.get("SYMBIX_PIXIV_PET_DIR")
    if env:
        return Path(env)
    # scripts → pet-forge → installed_skills → skill → Symbix_sdk → backend → 项目根
    project_root = _SCRIPTS.parents[5]
    return project_root / "Symbix_frontend" / "public" / "pixiv_pet"


def _existing_style(out: Path) -> str | None:
    """读旧产物的风格标记(pet.json / theme.json)。

    重烘焙时必须沿用主题原有风格:否则给一只平滑矢量老皮肤点「再烘焙」,
    会把它一口气变成像素风(用户没要求过的外观变化)。
    旧产物没有 style 字段 = 历史主题,当年只有平滑矢量一种画法 → 按 smooth 处理。
    """
    import json

    legacy = False
    for filename in ("pet.json", "theme.json"):
        path = out / filename
        if not path.is_file():
            continue
        legacy = True
        try:
            style = json.loads(path.read_text(encoding="utf-8")).get("style")
        except Exception:
            style = None
        if style in ("pixel", "smooth"):
            return style
    return "smooth" if legacy else None


def _shift_horizontally(im, dx: int):
    """整帧水平平移 dx 像素(透明填充,超出部分裁掉;不做环绕)。"""
    from PIL import Image

    if dx == 0:
        return im
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (dx, 0))
    return out


def _post_process_row(
    row: dict[str, Any], variants: dict[str, Any], frames_root: Path
) -> None:
    """在渲染好的 PNG 上做镜像 / 水平滚动(running 系专用)。

    比在 SVG 层做稳:负 scale 在部分渲染器上会渲染成空白,而 body 的位移动画
    还会把「滚动位移」覆盖掉。
    """
    from PIL import Image, ImageOps

    home = row["home"]
    var = variants.get(home) or {}
    n_frames = int(row.get("frames") or 6)
    mirror_flag = var.get("mirror")
    use_mirror = bool(mirror_flag) if mirror_flag is not None else home == "runningLeft"
    scroll_dx = float(var.get("scroll_dx") or 0.0)
    if not use_mirror and not scroll_dx:
        return

    row_dir = frames_root / home
    for f in range(n_frames):
        fp = row_dir / f"frame_{f:02d}.png"
        if not fp.exists():
            continue
        im = Image.open(fp).convert("RGBA")
        if scroll_dx:
            t = f / max(n_frames - 1, 1)
            im = _shift_horizontally(im, round(math.sin(t * math.tau) * scroll_dx * 0.5))
        if use_mirror:
            im = ImageOps.mirror(im)
        im.save(fp, format="PNG")


def build_theme(
    *,
    name: str,
    rig_path: str | Path,
    states_path: str | Path,
    out_dir: str | Path | None = None,
    description: str = "",
    palette: dict[str, str] | None = None,
    bake: bool = True,
    keep_frames: bool = False,
    render_scale: int = 2,
    nearest: bool = False,
    pixel: bool | None = None,
    allow_template_fallback: bool = False,
) -> dict[str, Any]:
    """跑完整流水线,返回结果摘要(供 Agent 汇报 / 端点返回)。

    allow_template_fallback: 校验（多次重试仍）失败时用 assets/fixtures 的模板 rig/states
    先行打包,标记 fallback=true 并回写 warnings。宁可上一个「丑但能动」的占位宠物,
    也不要一次产出都没有(否则用户得到的是零收获)。
    pixel: 像素画板模式(None = 自动:新主题像素风,重烘焙沿用旧产物的 style)。
    """
    if not (name or "").strip():
        raise ValueError("name 不能为空")

    warnings: list[str] = []
    fallback = False

    out = Path(out_dir) if out_dir else default_public_dir() / name
    if pixel is None:
        pixel = _existing_style(out) != "smooth"
    style = "pixel" if pixel else "smooth"

    svg = read_text(rig_path)
    # keyframes 先加载:校验阶段就能抓住「preset 指向不存在的部件 / 动画名未定义」
    keyframes = json.loads(read_text(_CONFIG_DIR / "keyframes.json"))
    rig_errors = validate_rig(svg, pixel=pixel)
    rig_errors, rig_warns = split_levels(rig_errors)
    for w in rig_warns:
        _add_warning(warnings, f"rig 像素契约提醒: [{w.get('rule')}] {w.get('where')}: {w.get('message')}")
    if rig_errors and allow_template_fallback:
        template_rig = _TEMPLATE_RIG_PIXEL if pixel else _TEMPLATE_RIG
        if not template_rig.is_file():
            raise ValueError(f"模板 rig 缺失,无法兜底: {template_rig}")
        fallback = True
        _add_warning(warnings, f"rig 校验失败,已改用模板占位图: {rig_errors}")
        svg = read_text(template_rig)
        # 模板自身不合法 = 安装坏了,照旧硬失败
        rig_errors, _ = split_levels(validate_rig(svg, pixel=pixel))
    if rig_errors:
        raise ValueError(f"rig 校验失败: {rig_errors}")

    states = derive_mirrors(json.loads(read_text(states_path)))
    part_ids = list_part_ids_from_svg(svg)
    state_errors = validate_states(states, part_ids=part_ids, keyframes=keyframes)
    if state_errors and allow_template_fallback:
        fallback = True
        _add_warning(warnings, f"states 校验失败,已改用模板占位动画: {state_errors}")
        states = derive_mirrors(json.loads(read_text(_TEMPLATE_STATES)))
        state_errors = validate_states(states, part_ids=part_ids, keyframes=keyframes)
    if state_errors:
        raise ValueError(f"states 校验失败: {state_errors}")

    # 配色优先级:显式入参 > 旧 theme.json > rig 自带 style > pack_theme 默认值
    if palette is None:
        legacy = out / "theme.json"
        if legacy.is_file():
            try:
                saved = json.loads(legacy.read_text(encoding="utf-8")).get("palette")
                if isinstance(saved, dict) and saved:
                    palette = saved
            except Exception:
                palette = None
        if palette is None:
            palette = palette_from_svg(svg) or None

    theme = pack_theme(
        name=name,
        svg_text=svg,
        states=states,
        out_dir=out,
        description=description,
        palette=palette,
    )
    result: dict[str, Any] = {
        "name": name,
        "out_dir": str(out),
        "slug": theme.get("slug"),
        "capabilities": theme.get("capabilities"),
        "parts": theme.get("parts"),
        "palette": theme.get("palette"),
        "baked": False,
        "fallback": fallback,
        "style": style,
        "warnings": warnings,
    }
    theme["fallback"] = fallback
    theme["style"] = style
    theme["warnings"] = list(warnings)
    write_json(out / "theme.json", theme)
    if not bake:
        return result

    mapping = json.loads(read_text(_CONFIG_DIR / "spritesheet_map.json"))
    variants = mapping.get("variants") or {}
    mapping_rows = mapping.get("rows") or []
    # 烘焙用同一套调色板(与上面写进 base.svg 的一致),否则 render_pil 会整只兜底黑
    bake_palette = theme.get("palette") or None

    frames_root = Path(tempfile.mkdtemp(prefix="petforge_bake_"))
    try:
        total, ok = 0, 0
        for row in mapping_rows:
            paths = bake_row(
                svg,
                states,
                row,
                variants,
                keyframes,
                frames_root,
                render_scale=render_scale,
                nearest=nearest,
                pixel=pixel,
                raster_post=True,  # 镜像/滚动由 _post_process_row 在 PNG 上做
                palette=bake_palette,
                warnings=warnings,
            )
            _post_process_row(row, variants, frames_root)
            total += int(row.get("frames") or 6)
            ok += len(paths)

        packed = pack_frames(frames_root, out, mapping)
        if keep_frames:
            shutil.copytree(frames_root, out / "frames", dirs_exist_ok=True)
    finally:
        shutil.rmtree(frames_root, ignore_errors=True)

    sheet_ok = bool(packed.get("webp") or packed.get("png"))
    if packed["missing"]:
        _add_warning(warnings, f"有 {len(packed['missing'])} 帧缺失(已填透明),动画会局部闪空")
    # 烘焙期的警告(缺失帧 / 动画没作用到部件)也要进 theme.json,与 pet.json 保持一致
    theme["warnings"] = list(warnings)
    write_json(out / "theme.json", theme)
    write_json(
        out / "pet.json",
        {
            "id": out.name,
            "displayName": name,
            "description": description,
            "spritesheetPath": "spritesheet.webp",
            "kind": "person",
            # 帧契约:后端/前端拿它校验 spritesheet 尺寸,尺寸不符就拒绝切换(避免切片错位)
            "frameWidth": FRAME_W,
            "frameHeight": FRAME_H,
            "columns": COLS,
            "rows": len(mapping_rows),
            "baked": sheet_ok,
            "missingFrames": packed["missing"],
            "fallback": fallback,
            "style": style,
            "warnings": warnings,
        },
    )

    result.update(
        {
            "baked": True,
            "frames_ok": ok,
            "frames_total": total,
            "missing_frames": packed["missing"],
            "spritesheet": str(packed["webp"] or packed["png"]),
            "fallback": fallback,
            "style": style,
            "warnings": warnings,
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pet-forge 一键构建(校验+烘焙+打包+pet.json)")
    ap.add_argument("-n", "--name", required=True, help="皮肤名(会作为输出目录名)")
    ap.add_argument("--rig", required=True, help="base.svg 路径")
    ap.add_argument("--states", required=True, help="states.json 路径")
    ap.add_argument("-o", "--out", default=None, help="输出目录(默认推导到前端 public/pixiv_pet/<name>)")
    ap.add_argument("-d", "--description", default="")
    ap.add_argument("--palette", default=None, help="可选 JSON: {\"--pet-primary\":\"#fff\",...}")
    ap.add_argument("--no-bake", action="store_true", help="只打包 rig 三件套,不烘焙 spritesheet")
    ap.add_argument("--keep-frames", action="store_true", help="保留逐帧 PNG(调试用)")
    ap.add_argument("--scale", type=int, default=2, help="渲染超采样倍数(默认 2 = 抗锯齿;像素风用 1 配 --nearest)")
    ap.add_argument("--nearest", action="store_true", help="NEAREST 降采样(保硬边)")
    ap.add_argument("--style", choices=("auto", "pixel", "smooth"), default="auto",
                    help="画风(auto=新主题像素风/重烘焙沿用原风格; pixel=强制像素画板; smooth=平滑矢量)")
    ap.add_argument(
        "--template-fallback",
        action="store_true",
        help="校验(重试后仍)失败时用模板 rig/states 兑底打包,并标记 fallback=true",
    )
    args = ap.parse_args(argv)

    palette = None
    if args.palette:
        try:
            palette = json.loads(args.palette)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: --palette 不是合法 JSON: {e}", file=sys.stderr)
            return 2

    try:
        result = build_theme(
            name=args.name,
            rig_path=args.rig,
            states_path=args.states,
            out_dir=args.out,
            description=args.description,
            palette=palette,
            bake=not args.no_bake,
            keep_frames=args.keep_frames,
            render_scale=args.scale,
            nearest=args.nearest,
            pixel=None if args.style == "auto" else args.style == "pixel",
            allow_template_fallback=args.template_fallback,
        )
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print("OK: " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
