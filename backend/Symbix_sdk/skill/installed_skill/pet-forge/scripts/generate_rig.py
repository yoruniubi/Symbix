"""调用 LLM 生成 base.svg rig，校验失败自动重试（最多 N 次）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _common import (  # noqa: E402
    extract_svg,
    format_errors,
    skill_root,
    with_llm,
    write_text,
)
from validate_rig import validate_rig  # noqa: E402

RIG_SYSTEM = """你是桌宠 SVG rig 生成器。只输出一个合法的 <svg> 文档，不要解释、不要 markdown 代码块。

硬约束：
1. 根节点 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
2. viewBox 必须精确等于 "0 0 200 200"
3. 每个部件必须是 <g id="部件id">，禁止裸露顶层 path/circle
4. 必需部件（缺一不可）：body, eye-left, eye-right, pupil-left, pupil-right, mouth
5. 可选部件仅当用户描述提到时才生成：limb-left, limb-right, ear-left, ear-right, tail, accessory
6. 颜色只能用 CSS 变量：var(--pet-primary) var(--pet-secondary) var(--pet-accent) var(--pet-eye) var(--pet-pupil) var(--pet-line)
7. 禁止写死 hex/rgb/hsl 颜色
8. 每个必需部件 g 必须显式 transform-origin（属性或 style）
9. 禁止：script、foreignObject、外部 image URL、任何 on* 事件属性、javascript: URL
10. 风格：宠物安全——简洁圆润，小尺寸仍可辨识，无文字

建议 transform-origin：
- body: 100px 120px
- eye-left / pupil-left: 80px 90px
- eye-right / pupil-right: 120px 90px
- mouth: 100px 130px
"""


class RigGenerationError(RuntimeError):
    def __init__(self, message: str, errors: list[dict]):
        super().__init__(message)
        self.errors = errors


def generate_rig(
    description: str,
    *,
    name: str = "Pet",
    max_retries: int = 3,
    llm_complete: Optional[Callable[[str, str], str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> str:
    """生成通过校验的 SVG 文本。失败抛 RigGenerationError。"""
    complete = with_llm(llm_complete)
    log = progress or (lambda m: print(m, file=sys.stderr))

    log(f"正在勾勒 {name} 的样子…")
    user = (
        f"请根据下列描述生成桌宠 base SVG rig：\n\n"
        f"名字：{name}\n"
        f"描述：{description}\n\n"
        f"只输出完整 <svg>...</svg>。"
    )

    last_svg = ""
    last_errors: list[dict] = []

    for attempt in range(1, max_retries + 1):
        log(f"[rig] attempt {attempt}/{max_retries}")
        if attempt == 1:
            raw = complete(RIG_SYSTEM, user)
        else:
            retry_user = (
                "上一次输出未通过校验。请输出**完整**修正后的 <svg>（不要 diff/patch）。\n\n"
                f"错误列表：\n{format_errors(last_errors)}\n\n"
                f"上一次输出：\n{last_svg}\n\n"
                f"描述：{description}\n名字：{name}"
            )
            raw = complete(RIG_SYSTEM, retry_user)

        svg = extract_svg(raw)
        last_svg = svg
        errors = validate_rig(svg)
        if not errors:
            log(f"[rig] OK on attempt {attempt}")
            return svg

        last_errors = errors
        log(f"[rig] {len(errors)} error(s), will retry…")
        for e in errors[:8]:
            log(f"  - [{e.get('rule')}] {e.get('where', e.get('part', ''))}: {e.get('message')}")

    raise RigGenerationError(
        f"rig 生成在 {max_retries} 次尝试后仍失败",
        last_errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate pet-forge base.svg via LLM")
    parser.add_argument("-d", "--description", required=True, help="pet description")
    parser.add_argument("-n", "--name", default="Pet")
    parser.add_argument("-o", "--output", default="base.svg")
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args(argv)

    try:
        svg = generate_rig(
            args.description,
            name=args.name,
            max_retries=args.max_retries,
        )
    except RigGenerationError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        print(format_errors(e.errors), file=sys.stderr)
        return 1

    write_text(args.output, svg + ("\n" if not svg.endswith("\n") else ""))
    print(f"OK: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
