"""校验 states.json：必需状态、部件引用、动画白名单、镜像一致性。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    MIRROR_MAP,
    REQUIRED_STATES,
    expand_part_keys,
    list_part_ids_from_svg,
    parse_animation_decl,
    read_text,
)


def _parts_in_rules(rules: dict[str, Any]) -> set[str]:
    present: set[str] = set()
    for key in rules.keys():
        for p in expand_part_keys(str(key)):
            present.add(p)
    return present


def validate_states(
    states: dict[str, Any],
    *,
    part_ids: Optional[Iterable[str]] = None,
    require_all_states: bool = True,
    check_mirrors: bool = True,
) -> list[dict[str, Any]]:
    """返回结构化错误列表。空 = 通过。"""
    errors: list[dict[str, Any]] = []

    if not isinstance(states, dict):
        return [{"rule": "type", "message": "states 必须是 JSON 对象"}]

    part_set = set(part_ids) if part_ids is not None else None

    if require_all_states:
        for st in REQUIRED_STATES:
            if st not in states:
                errors.append(
                    {
                        "rule": "required_state",
                        "state": st,
                        "where": st,
                        "message": f"缺少必需状态: {st}",
                    }
                )

    for state_name, rules in states.items():
        if not isinstance(rules, dict):
            errors.append(
                {
                    "rule": "state_type",
                    "state": state_name,
                    "where": state_name,
                    "message": f"状态 {state_name} 必须是对象",
                }
            )
            continue

        present = _parts_in_rules(rules)

        for key, value in rules.items():
            parts = expand_part_keys(str(key))
            if not parts:
                errors.append(
                    {
                        "rule": "empty_part_key",
                        "state": state_name,
                        "where": state_name,
                        "message": f"空的部件键: {key!r}",
                    }
                )
                continue

            for part in parts:
                if part_set is not None and part not in part_set:
                    errors.append(
                        {
                            "rule": "unknown_part",
                            "state": state_name,
                            "part": part,
                            "where": f"{state_name}/{part}",
                            "message": f"部件 id 不在 rig 中: {part}",
                        }
                    )

            if not isinstance(value, str):
                errors.append(
                    {
                        "rule": "anim_type",
                        "state": state_name,
                        "part": str(key),
                        "where": f"{state_name}/{key}",
                        "message": f"动画声明必须是字符串，实际为 {type(value).__name__}",
                    }
                )
                continue

            _parsed, err = parse_animation_decl(value)
            if err:
                errors.append(
                    {
                        "rule": "anim_decl",
                        "state": state_name,
                        "part": str(key),
                        "where": f"{state_name}/{key}",
                        "message": err,
                    }
                )

        if check_mirrors:
            for right, left in MIRROR_MAP.items():
                has_r = right in present
                has_l = left in present
                if has_r != has_l:
                    missing = left if has_r else right
                    other = right if has_r else left
                    errors.append(
                        {
                            "rule": "mirror_consistency",
                            "state": state_name,
                            "part": missing,
                            "where": f"{state_name}/{missing}",
                            "message": (
                                f"镜像不一致：有 {other} 但没有 {missing}。"
                                "请运行 derive_mirrors 或补全规则。"
                            ),
                        }
                    )

    return errors


def validate_states_file(
    states_path: str | Path,
    *,
    rig_svg_path: str | Path | None = None,
    part_ids: Optional[Iterable[str]] = None,
) -> list[dict[str, Any]]:
    data = json.loads(read_text(states_path))
    ids = list(part_ids) if part_ids is not None else None
    if ids is None and rig_svg_path:
        ids = list_part_ids_from_svg(read_text(rig_svg_path))
    return validate_states(data, part_ids=ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pet-forge states.json")
    parser.add_argument("states", help="path to states.json")
    parser.add_argument("--rig", help="optional base.svg to check part ids")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-mirror",
        action="store_true",
        help="skip mirror consistency (before derive_mirrors)",
    )
    args = parser.parse_args(argv)

    data = json.loads(read_text(args.states))
    part_ids = list_part_ids_from_svg(read_text(args.rig)) if args.rig else None
    errors = validate_states(
        data,
        part_ids=part_ids,
        check_mirrors=not args.no_mirror,
    )

    if args.json:
        print(json.dumps(errors, ensure_ascii=False, indent=2))
    else:
        if not errors:
            print("OK: states valid")
        else:
            print(f"FAIL: {len(errors)} error(s)")
            for e in errors:
                print(f"  - [{e.get('rule')}] {e.get('where', '')}: {e.get('message')}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
