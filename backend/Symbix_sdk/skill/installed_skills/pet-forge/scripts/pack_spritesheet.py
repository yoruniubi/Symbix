"""Script B — 拼装:把脚本A产出的 PNG 帧序列按 8×9 网格排布成 spritesheet.webp。

用法:
    python pack_spritesheet.py -s build/mochi -o dist/mochi \
        [--map config/spritesheet_map.json]

说明:
    1. 读 spritesheet_map.json 的行顺序(rows),每行读 build/{name}/{home}/frame_NN.png。
    2. 按 8×9 网格纯拼接(192×208 帧 → 1536×1872),帧缺失填透明。
    3. 写 spritesheet.webp(与 Home.vue 契约一致,前端零改动)。

帧尺寸/网格不进 CLI(契约固定:Home.vue ROWS 硬编码 9 行)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import read_text  # noqa: E402

FRAME_W, FRAME_H = 192, 208
COLS, ROWS = 8, 9


def pack_frames(src_root: str | Path, out_dir: str | Path, mapping: dict) -> dict:
    """把帧序列目录拼成 spritesheet.png / spritesheet.webp。

    返回 {"png": Path, "webp": Path|None, "missing": list[str]}。
    缺失帧填透明,不报错(由调用方决定是否接受)。
    """
    from PIL import Image  # 局部 import,避免无 PIL 时整个模块崩

    src_root = Path(src_root)
    sheet = Image.new("RGBA", (COLS * FRAME_W, ROWS * FRAME_H), (0, 0, 0, 0))
    missing: list[str] = []

    for r, row in enumerate(mapping.get("rows", [])):
        home = row["home"]
        n_frames = int(row.get("frames") or 6)
        row_dir = src_root / home
        for c in range(COLS):
            if c >= n_frames:
                continue
            fp = row_dir / f"frame_{c:02d}.png"
            if not fp.exists():
                missing.append(f"{home}/frame_{c:02d}")
                continue
            try:
                fr = Image.open(fp).convert("RGBA")
            except Exception as e:  # noqa: BLE001
                missing.append(f"{home}/frame_{c:02d}({e})")
                continue
            x, y = c * FRAME_W, r * FRAME_H
            sheet.paste(fr, (x, y), fr)

    if missing:
        print(f"[warn] 缺失/损坏帧 {len(missing)} 个(填透明):")
        for m in missing[:20]:
            print(f"  - {m}")
        if len(missing) > 20:
            print(f"  ... 共 {len(missing)} 个")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "spritesheet.png"
    sheet.save(out_png, format="PNG")
    print(f"PNG 拼装完: {out_png} ({sheet.size[0]}x{sheet.size[1]})")

    # WebP(Home.vue 实际加载的格式)
    out_webp: Path | None = None
    try:
        out_webp = out_dir / "spritesheet.webp"
        sheet.save(out_webp, format="WEBP", lossless=True, method=6)
        print(f"WebP 输出: {out_webp} ({sheet.size[0]}x{sheet.size[1]})")
    except Exception as e:  # noqa: BLE001
        out_webp = None
        print(f"[warn] WebP 编码失败(仅 PNG 可用): {e}")

    return {"png": out_png, "webp": out_webp, "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(description="拼装帧序列为 spritesheet.webp")
    ap.add_argument("-s", "--src", required=True, help="脚本A输出根目录(build/{name})")
    ap.add_argument("-o", "--out", default="dist", help="输出目录")
    ap.add_argument("--map", default=None, help="spritesheet_map.json(默认 config/spritesheet_map.json)")
    args = ap.parse_args()

    cfg = Path(__file__).resolve().parent.parent / "config"
    map_path = Path(args.map) if args.map else cfg / "spritesheet_map.json"
    mapping = json.loads(read_text(map_path))

    result = pack_frames(args.src, args.out, mapping)
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())