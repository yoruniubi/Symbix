"""分批生成 states.json 片段；每批独立重试；最后 derive_mirrors。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    STATE_BATCHES,
    extract_json_obj,
    format_errors,
    list_part_ids_from_svg,
    read_text,
    with_llm,
    write_json,
)
from derive_mirrors import derive_mirrors  # noqa: E402
from validate_states import validate_states  # noqa: E402

STATES_SYSTEM_TMPL = """你是桌宠 states.json 片段生成器。只输出合法 JSON 对象，不要解释、不要 markdown 代码块。

硬约束：
1. 只生成本批次要求的状态键，不要多写
2. 动画名只能从白名单选：breathe, breathe-slow, blink, bounce, wave, frown, close, open-startled, lean-in, perk, sway-slow
3. 禁止自造动画名
4. 规则值格式：动画名 时长 缓动 次数（次数为正整数或 infinite）
5. 键为部件 id；多个部件共享同一动画时用逗号分隔（如 eye-right,pupil-right）
6. 只写 -right / 中心部件（body, mouth, tail, accessory）；不要写 -left（脚本会镜像补全）
7. 引用的部件 id 必须存在于下列列表：{part_ids}
8. 不确定时优先 breathe 或 blink
"""


class StatesGenerationError(RuntimeError):
    def __init__(self, message: str, errors: list[dict], batch: tuple[str, ...] | None = None):
        super().__init__(message)
        self.errors = errors
        self.batch = batch


def _system(part_ids: list[str]) -> str:
    return STATES_SYSTEM_TMPL.format(part_ids=", ".join(part_ids))


def generate_batch(
    batch_states: tuple[str, ...] | list[str],
    *,
    part_ids: list[str],
    name: str = "Pet",
    description: str = "",
    max_retries: int = 3,
    llm_complete: Optional[Callable[[str, str], str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """生成单个批次的 states 片段（未镜像）。"""
    complete = with_llm(llm_complete)
    log = progress or (lambda m: print(m, file=sys.stderr))
    batch = tuple(batch_states)
    system = _system(part_ids)

    user = (
        "为本批次状态生成动画规则 JSON。\n\n"
        f"宠物名：{name}\n"
        f"描述：{description}\n"
        f"本批状态：{', '.join(batch)}\n"
        f"可用部件：{', '.join(part_ids)}\n\n"
        '只输出 JSON，例如：{"idle": {"body": "breathe 2.4s ease-in-out infinite"}}'
    )

    last_json = ""
    last_errors: list[dict] = []

    for attempt in range(1, max_retries + 1):
        log(f"[states {','.join(batch)}] attempt {attempt}/{max_retries}")
        if attempt == 1:
            raw = complete(system, user)
        else:
            retry_user = (
                "上一次 JSON 未通过校验。请输出**完整**本批 JSON（覆盖整批，不要 patch）。\n\n"
                f"错误列表：\n{format_errors(last_errors)}\n\n"
                f"上一次输出：\n{last_json}\n\n"
                f"本批状态：{', '.join(batch)}\n"
                f"可用部件：{', '.join(part_ids)}"
            )
            raw = complete(system, retry_user)

        try:
            obj = extract_json_obj(raw)
        except Exception as e:
            last_errors = [{"rule": "json_parse", "message": str(e)}]
            last_json = raw
            log(f"[states] JSON parse failed: {e}")
            continue

        if not isinstance(obj, dict):
            last_errors = [{"rule": "type", "message": "输出必须是 JSON 对象"}]
            last_json = json.dumps(obj, ensure_ascii=False)
            continue

        # 只保留本批键
        fragment = {k: v for k, v in obj.items() if k in batch}
        last_json = json.dumps(fragment, ensure_ascii=False, indent=2)

        # 批次内校验：不要求全部 6 状态；镜像先不查
        errors = validate_states(
            fragment,
            part_ids=part_ids,
            require_all_states=False,
            check_mirrors=False,
        )
        # 缺本批状态也算错
        for st in batch:
            if st not in fragment:
                errors.append(
                    {
                        "rule": "batch_missing_state",
                        "state": st,
                        "where": st,
                        "message": f"本批缺少状态: {st}",
                    }
                )

        if not errors:
            log(f"[states {','.join(batch)}] OK")
            return fragment

        last_errors = errors
        log(f"[states] {len(errors)} error(s), retry…")

    raise StatesGenerationError(
        f"批次 {batch} 在 {max_retries} 次后仍失败",
        last_errors,
        batch=batch,
    )


def generate_states_all(
    *,
    part_ids: list[str],
    name: str = "Pet",
    description: str = "",
    max_retries: int = 3,
    llm_complete: Optional[Callable[[str, str], str]] = None,
    progress: Optional[Callable[[str], None]] = None,
    apply_mirrors: bool = True,
) -> dict[str, Any]:
    """跑全部 3 批，合并后可选镜像补全。"""
    log = progress or (lambda m: print(m, file=sys.stderr))
    log(f"正在给 {name} 编排动作…")
    merged: dict[str, Any] = {}

    for batch in STATE_BATCHES:
        frag = generate_batch(
            batch,
            part_ids=part_ids,
            name=name,
            description=description,
            max_retries=max_retries,
            llm_complete=llm_complete,
            progress=progress,
        )
        merged.update(frag)

    if apply_mirrors:
        merged = derive_mirrors(merged)

    # 最终全量校验
    errors = validate_states(merged, part_ids=part_ids, require_all_states=True, check_mirrors=True)
    if errors:
        raise StatesGenerationError("全部批次合并后校验失败", errors)

    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch-generate states.json via LLM")
    parser.add_argument("--rig", required=True, help="base.svg path (for part ids)")
    parser.add_argument("-d", "--description", default="")
    parser.add_argument("-n", "--name", default="Pet")
    parser.add_argument("-o", "--output", default="states.json")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--no-mirrors", action="store_true")
    args = parser.parse_args(argv)

    svg = read_text(args.rig)
    part_ids = list_part_ids_from_svg(svg)
    if not part_ids:
        print("FAIL: no part ids found in rig", file=sys.stderr)
        return 1

    try:
        states = generate_states_all(
            part_ids=part_ids,
            name=args.name,
            description=args.description,
            max_retries=args.max_retries,
            apply_mirrors=not args.no_mirrors,
        )
    except StatesGenerationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        print(format_errors(e.errors), file=sys.stderr)
        return 1

    write_json(args.output, states)
    print(f"OK: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
