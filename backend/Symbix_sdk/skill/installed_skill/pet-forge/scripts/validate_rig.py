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
    VIEWBOX_EXACT,
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


def validate_rig(svg_text: str) -> list[dict[str, Any]]:
    """校验 SVG 文本，返回错误列表。空列表 = 通过。"""
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
    if vb_norm != VIEWBOX_EXACT:
        errors.append(
            {
                "rule": "viewBox",
                "where": "svg",
                "message": f'viewBox 必须精确为 "{VIEWBOX_EXACT}"，实际为 {vb!r}',
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

    # 写死颜色
    if _HARD_COLOR_RE.search(text):
        # 允许在注释外；简单整体扫描
        errors.append(
            {
                "rule": "no_hardcoded_color",
                "message": "检测到写死颜色（#hex / rgb() / hsl()）。请改用 var(--pet-*)",
            }
        )

    return errors


def validate_rig_file(path: str | Path) -> list[dict[str, Any]]:
    return validate_rig(read_text(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pet-forge base.svg rig")
    parser.add_argument("svg", help="path to SVG file")
    parser.add_argument("--json", action="store_true", help="print JSON errors")
    args = parser.parse_args(argv)

    errors = validate_rig_file(args.svg)
    if args.json:
        print(json.dumps(errors, ensure_ascii=False, indent=2))
    else:
        if not errors:
            print("OK: rig valid")
        else:
            print(f"FAIL: {len(errors)} error(s)")
            for e in errors:
                where = e.get("where") or e.get("part") or ""
                print(f"  - [{e.get('rule')}] {where}: {e.get('message')}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
