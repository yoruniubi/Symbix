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


def pack_theme(
    *,
    name: str,
    svg_text: str,
    states: dict[str, Any],
    out_dir: str | Path,
    version: str = "1.0.0",
    description: str = "",
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """写入 out_dir/{base.svg,states.json,theme.json}，返回 theme dict。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rig_errors = validate_rig(svg_text)
    if rig_errors:
        raise ValueError(f"rig 校验失败: {rig_errors}")

    part_ids = list_part_ids_from_svg(svg_text)
    state_errors = validate_states(states, part_ids=part_ids)
    if state_errors:
        raise ValueError(f"states 校验失败: {state_errors}")

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
        "palette": {
            "--pet-primary": "#7C9EFF",
            "--pet-secondary": "#B8C9FF",
            "--pet-accent": "#FFB4A2",
            "--pet-eye": "#FFFFFF",
            "--pet-pupil": "#2A2A2A",
            "--pet-line": "#1A1A1A",
        },
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
