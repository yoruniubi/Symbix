"""只修复单个状态：不重跑整批 generate_states_batch。"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    extract_json_obj,
    format_errors,
    list_part_ids_from_svg,
    read_text,
    with_llm,
    write_json,
)
from derive_mirrors import derive_mirrors_for_state  # noqa: E402
from validate_states import validate_states  # noqa: E402

REPAIR_SYSTEM = """你是桌宠单状态修复器。只输出一个 JSON 对象：{"状态名": { ...规则... }}，不要解释。

硬约束：
1. 只修复指定的那一个状态
2. 动画名只能从白名单选：breathe, breathe-slow, blink, bounce, wave, frown, close, open-startled, lean-in, perk, sway-slow
3. 规则值格式：动画名 时长 缓动 次数
4. 只写 -right / 中心部件；不要写 -left
5. 引用的部件必须在可用列表中
"""


class RepairError(RuntimeError):
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


def repair_state(
    state_name: str,
    *,
    part_ids: list[str],
    errors: list[dict],
    previous_state: Optional[dict[str, Any]] = None,
    name: str = "Pet",
    description: str = "",
    max_retries: int = 3,
    llm_complete: Optional[Callable[[str, str], str]] = None,
    progress: Optional[Callable[[str], None]] = None,
    apply_mirrors: bool = True,
) -> dict[str, Any]:
    """返回修复后的单状态规则对象（已可选镜像）。"""
    complete = with_llm(llm_complete)
    log = progress or (lambda m: print(m, file=sys.stderr))

    prev = json.dumps(previous_state or {}, ensure_ascii=False, indent=2)
    user = (
        f"修复状态 `{state_name}`。\n\n"
        f"错误列表：\n{format_errors(errors)}\n\n"
        f"可用部件：{', '.join(part_ids)}\n"
        f"上一次该状态内容：\n{prev}\n\n"
        f"宠物名：{name}\n描述：{description}\n"
    )

    last_errors = list(errors)
    last_raw = prev

    for attempt in range(1, max_retries + 1):
        log(f"[repair {state_name}] attempt {attempt}/{max_retries}")
        raw = complete(REPAIR_SYSTEM, user if attempt == 1 else (
            "请再次输出完整单状态 JSON。\n\n"
            f"错误列表：\n{format_errors(last_errors)}\n\n"
            f"上一次输出：\n{last_raw}\n"
            f"状态名：{state_name}\n可用部件：{', '.join(part_ids)}"
        ))
        last_raw = raw
        try:
            obj = extract_json_obj(raw)
        except Exception as e:
            last_errors = [{"rule": "json_parse", "message": str(e)}]
            continue

        if not isinstance(obj, dict):
            last_errors = [{"rule": "type", "message": "必须是 JSON 对象"}]
            continue

        # 允许 {"state": {...}} 或直接 {...规则}
        if state_name in obj and isinstance(obj[state_name], dict):
            rules = obj[state_name]
        elif all(isinstance(v, str) for v in obj.values()):
            rules = obj
        else:
            # 若只有一个 key 且是 dict
            if len(obj) == 1 and isinstance(next(iter(obj.values())), dict):
                rules = next(iter(obj.values()))
            else:
                last_errors = [
                    {
                        "rule": "shape",
                        "message": f"期望 {{\"{state_name}\": {{...}}}} 或规则对象",
                    }
                ]
                continue

        if apply_mirrors:
            rules = derive_mirrors_for_state(rules)

        frag = {state_name: rules}
        check = validate_states(
            frag,
            part_ids=part_ids,
            require_all_states=False,
            check_mirrors=True,
        )
        if not check:
            log(f"[repair {state_name}] OK")
            return rules

        last_errors = check
        log(f"[repair] {len(check)} error(s)")

    raise RepairError(f"状态 {state_name} 修复失败", last_errors)


def repair_in_states_file(
    states_path: str | Path,
    state_name: str,
    *,
    rig_path: str | Path,
    name: str = "Pet",
    description: str = "",
    max_retries: int = 3,
    llm_complete: Optional[Callable[[str, str], str]] = None,
) -> dict[str, Any]:
    """就地修复 states.json 中的一个状态，其它状态不变。"""
    states = json.loads(read_text(states_path))
    part_ids = list_part_ids_from_svg(read_text(rig_path))
    prev = states.get(state_name) if isinstance(states.get(state_name), dict) else {}

    # 先对当前全量做校验，筛出该状态相关错误
    all_err = validate_states(states, part_ids=part_ids)
    state_err = [e for e in all_err if e.get("state") == state_name or e.get("where", "").startswith(state_name)]
    if not state_err and state_name in states:
        # 无错误也允许强制重生成：给一个占位错误提示
        state_err = [
            {
                "rule": "forced_repair",
                "state": state_name,
                "message": "用户请求强制修复该状态",
            }
        ]

    new_rules = repair_state(
        state_name,
        part_ids=part_ids,
        errors=state_err or [{"rule": "missing", "message": f"缺少状态 {state_name}"}],
        previous_state=prev,
        name=name,
        description=description,
        max_retries=max_retries,
        llm_complete=llm_complete,
    )

    new_states = copy.deepcopy(states)
    new_states[state_name] = new_rules
    write_json(states_path, new_states)
    return new_states


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair a single pet state")
    parser.add_argument("states", help="states.json path")
    parser.add_argument("state_name", help="e.g. happy")
    parser.add_argument("--rig", required=True)
    parser.add_argument("-n", "--name", default="Pet")
    parser.add_argument("-d", "--description", default="")
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args(argv)

    try:
        repair_in_states_file(
            args.states,
            args.state_name,
            rig_path=args.rig,
            name=args.name,
            description=args.description,
            max_retries=args.max_retries,
        )
    except RepairError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        print(format_errors(e.errors), file=sys.stderr)
        return 1

    print(f"OK: repaired {args.state_name} in {args.states}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
