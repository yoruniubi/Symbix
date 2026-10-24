"""镜像部件规则推导（纯函数，无 LLM）。

规则：
- 若状态里出现 right 规则但没有对应 left → 复制给 left
- 若 left/right 都被显式写出 → 不覆盖 left
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import MIRROR_MAP, expand_part_keys, read_text, write_json  # noqa: E402


def _parts_present_in_state(rules: dict[str, Any]) -> set[str]:
    present: set[str] = set()
    for key in rules.keys():
        for p in expand_part_keys(str(key)):
            present.add(p)
    return present


def derive_mirrors_for_state(rules: dict[str, Any]) -> dict[str, Any]:
    """对单个状态规则对象补全镜像。返回新 dict，不修改入参。"""
    if not isinstance(rules, dict):
        return rules

    out: dict[str, Any] = copy.deepcopy(rules)
    present = _parts_present_in_state(out)

    # 逐条规则：若 key 含 right 部件且对应 left 完全未出现，则追加 left 键
    additions: dict[str, Any] = {}
    for key, value in list(out.items()):
        parts = expand_part_keys(str(key))
        if not parts:
            continue

        new_parts: list[str] = []
        changed = False
        for p in parts:
            new_parts.append(p)
            left = MIRROR_MAP.get(p)
            if not left:
                continue
            # 若 left 已在任何 key 中出现（显式），不覆盖/不追加
            if left in present:
                continue
            new_parts.append(left)
            changed = True
            present.add(left)

        if changed:
            # 若原 key 已是 multi，或我们扩展了 multi
            new_key = ",".join(new_parts)
            if new_key != key:
                # 保留原 key 不动；另写一条仅 left 的规则，避免破坏原 key 语义
                # 更稳妥：给每个缺失 left 单独加一条同 value
                for p in parts:
                    left = MIRROR_MAP.get(p)
                    if left and left in new_parts and left not in expand_part_keys(str(key)):
                        # 单独 left key（若尚未存在）
                        if left not in present or left not in _parts_present_in_state(out):
                            # 检查 out 是否已有单独 left
                            already = any(
                                left in expand_part_keys(str(k)) for k in out.keys()
                            ) or any(
                                left in expand_part_keys(str(k)) for k in additions.keys()
                            )
                            if not already:
                                additions[left] = value

    out.update(additions)
    return out


def derive_mirrors(states: dict[str, Any]) -> dict[str, Any]:
    """对整个 states.json 对象补全镜像。"""
    if not isinstance(states, dict):
        raise TypeError("states 必须是 dict")
    result: dict[str, Any] = {}
    for state_name, rules in states.items():
        if isinstance(rules, dict):
            result[state_name] = derive_mirrors_for_state(rules)
        else:
            result[state_name] = rules
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive mirror animation rules")
    parser.add_argument("input", help="input states.json")
    parser.add_argument("-o", "--output", help="output path (default: stdout / overwrite)")
    parser.add_argument("--inplace", action="store_true", help="overwrite input")
    args = parser.parse_args(argv)

    data = json.loads(read_text(args.input))
    derived = derive_mirrors(data)

    if args.inplace:
        write_json(args.input, derived)
        print(f"OK: wrote mirrors inplace → {args.input}")
    elif args.output:
        write_json(args.output, derived)
        print(f"OK: wrote → {args.output}")
    else:
        print(json.dumps(derived, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
