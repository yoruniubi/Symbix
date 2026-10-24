"""打包 base.svg + states.json + theme.json。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    list_part_ids_from_svg,
    read_text,
    write_json,
    write_text,
)
from validate_rig import validate_rig  # noqa: E402
from validate_states import validate_states  # noqa: E402


_DEFAULT_PALETTE: dict[str, str] = {
    "--pet-primary": "#7C9EFF",
    "--pet-secondary": "#B8C9FF",
    "--pet-accent": "#FFB4A2",
    "--pet-eye": "#FFFFFF",
    "--pet-pupil": "#2A2A2A",
    "--pet-line": "#1A1A1A",
}

_PALETTE_VAR_RE = re.compile(r"(--pet-[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})")


def palette_from_svg(svg_text: str) -> dict[str, str]:
    """从 rig 根节点 style 里读回 --pet-* 变量(只读根标签,与 render_pil 的读法一致)。"""
    head = svg_text[: svg_text.find(">") + 1] if ">" in svg_text else svg_text
    return {k: v for k, v in _PALETTE_VAR_RE.findall(head)}


def resolve_palette(svg_text: str, override: dict[str, str] | None = None) -> dict[str, str]:
    """生效调色板 = 默认值 ← rig 自带 style ← 显式入参。

    render_pil 只认根 style 里的 --pet-*,rig 没声明就会整只落兜底黑。
    所以打包与烘焙都要先过这一层,保证交给渲染器的 SVG 自包含颜色。
    """
    pal = dict(_DEFAULT_PALETTE)
    pal.update(palette_from_svg(svg_text))
    if override:
        pal.update({k: v for k, v in override.items() if v})
    return pal


def compute_capabilities(part_ids: list[str]) -> list[str]:
    caps: list[str] = ["core_animation"]
    ids = set(part_ids)
    if "limb-left" in ids or "limb-right" in ids:
        caps.append("limb_animation")
    if "ear-left" in ids or "ear-right" in ids:
        caps.append("ear_animation")
    if "tail" in ids:
        caps.append("tail_animation")
    if "accessory" in ids:
        caps.append("accessory")
    return caps


def _inject_palette_to_svg(svg_text: str, palette: dict[str, str]) -> str:
    """把主题色注入 <svg> 根节点的 style 属性(如 style="--pet-primary:#7C9EFF;...")。
    让产物 base.svg 自包含颜色定义:浏览器 / 渲染器 / 文件面板直接打开即可看到颜色,
    不需要外部 CSS 注入。已有 style 则合并覆盖同名变量。
    """
    if not palette:
        return svg_text
    style_attr = ";".join(f"{k}:{v}" for k, v in palette.items())
    m = re.search(r"<svg\b[^>]*>", svg_text, re.S)
    if not m:
        return svg_text
    tag = m.group(0)
    if re.search(r'style\s*=\s*["\']', tag):
        new_tag = re.sub(r'style\s*=\s*"[^"]*"', f'style="{style_attr}"', tag, count=1)
    else:
        new_tag = tag[:-1] + f' style="{style_attr}">'
    return svg_text[: m.start()] + new_tag + svg_text[m.end():]


# 公开别名:烘焙链路也要用同一套注入逻辑
inject_palette_to_svg = _inject_palette_to_svg


def pack_theme(
    *,
    name: str,
    svg_text: str,
    states: dict[str, Any],
    out_dir: str | Path,
    version: str = "1.0.0",
    description: str = "",
    schema_path: str | Path | None = None,
    palette: dict[str, str] | None = None,
) -> dict[str, Any]:
    """写入 out_dir/{base.svg,states.json,theme.json},返回 theme dict。

    palette: 可选,覆盖默认主题色。用于参考图取色后落盘。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rig_errors = validate_rig(svg_text)
    if rig_errors:
        raise ValueError(f"rig 校验失败: {rig_errors}")

    part_ids = list_part_ids_from_svg(svg_text)
    state_errors = validate_states(states, part_ids=part_ids)
    if state_errors:
        raise ValueError(f"states 校验失败: {state_errors}")

    # 注入主题色到 base.svg 根节点,让产物自带颜色定义
    pal = dict(palette) if palette else dict(_DEFAULT_PALETTE)
    svg_text = _inject_palette_to_svg(svg_text, pal)

    write_text(out / "base.svg", svg_text if svg_text.endswith("\n") else svg_text + "\n")
    write_json(out / "states.json", states)

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower() or "pet"
    theme: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "version": version,
        "description": description,
        "rig": "base.svg",
        "states_file": "states.json",
        "capabilities": compute_capabilities(part_ids),
        "parts": part_ids,
        "palette": pal,
    }
    write_json(out / "theme.json", theme)

    if schema_path and Path(schema_path).is_file():
        _validate_against_schema(theme, Path(schema_path))

    return theme


def _validate_against_schema(theme: dict, schema_path: Path) -> None:
    """可选 jsonschema；未安装则做最小字段检查。"""
    try:
        import jsonschema  # type: ignore

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(theme, schema)
    except ImportError:
        required = ("name", "version", "rig", "states_file", "capabilities")
        missing = [k for k in required if k not in theme]
        if missing:
            raise ValueError(f"theme.json 缺少字段: {missing}")
    except Exception as e:
        raise ValueError(f"theme.schema.json 校验失败: {e}") from e


def pack_from_files(
    *,
    name: str,
    rig_path: str | Path,
    states_path: str | Path,
    out_dir: str | Path,
    version: str = "1.0.0",
    description: str = "",
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    svg = read_text(rig_path)
    states = json.loads(read_text(states_path))
    # 若源文件不在 out_dir，复制语义由 pack_theme 重写
    return pack_theme(
        name=name,
        svg_text=svg,
        states=states,
        out_dir=out_dir,
        version=version,
        description=description,
        schema_path=schema_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pack pet-forge theme bundle")
    parser.add_argument("--rig", required=True)
    parser.add_argument("--states", required=True)
    parser.add_argument("-o", "--out", required=True, help="output directory")
    parser.add_argument("-n", "--name", required=True)
    parser.add_argument("-d", "--description", default="")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--schema", default=None, help="optional theme.schema.json")
    args = parser.parse_args(argv)

    try:
        theme = pack_from_files(
            name=args.name,
            rig_path=args.rig,
            states_path=args.states,
            out_dir=args.out,
            version=args.version,
            description=args.description,
            schema_path=args.schema,
        )
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print(f"OK: packed theme → {args.out}")
    print(json.dumps({"name": theme["name"], "capabilities": theme["capabilities"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
