"""pet-forge 共享常量与工具函数（确定性，无 LLM）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Optional

# ── rig ──────────────────────────────────────────────────────────
REQUIRED_PARTS = (
    "body",
    "eye-left",
    "eye-right",
    "pupil-left",
    "pupil-right",
    "mouth",
)

OPTIONAL_PARTS = (
    "limb-left",
    "limb-right",
    "ear-left",
    "ear-right",
    "tail",
    "accessory",
)

# right (canonical) → left
MIRROR_MAP: dict[str, str] = {
    "eye-right": "eye-left",
    "pupil-right": "pupil-left",
    "limb-right": "limb-left",
    "ear-right": "ear-left",
}

VIEWBOX_EXACT = "0 0 200 200"

# ── states ───────────────────────────────────────────────────────
REQUIRED_STATES = (
    "idle",
    "listening",
    "happy",
    "concerned",
    "sleeping",
    "waking",
)

ANIMATION_WHITELIST = frozenset(
    {
        "breathe",
        "breathe-slow",
        "blink",
        "bounce",
        "wave",
        "frown",
        "close",
        "open-startled",
        "lean-in",
        "perk",
        "sway-slow",
    }
)

STATE_BATCHES: list[tuple[str, ...]] = [
    ("idle", "listening"),
    ("happy", "concerned"),
    ("sleeping", "waking"),
]

EASINGS = frozenset({"ease", "ease-in", "ease-out", "ease-in-out", "linear"})

# animation declaration: name duration easing iterations
_ANIM_RE = re.compile(
    r"^(?P<name>[a-z0-9-]+)\s+"
    r"(?P<duration>\d+(?:\.\d+)?(?:s|ms))\s+"
    r"(?P<easing>ease(?:-in)?(?:-out)?|linear)\s+"
    r"(?P<iters>\d+|infinite)$",
    re.I,
)

# hard-coded colors (forbidden)
_HARD_COLOR_RE = re.compile(
    r"(?:#(?:[0-9a-fA-F]{3,8})\b|"
    r"\brgba?\s*\(|"
    r"\bhsla?\s*\()",
)

_ON_ATTR_RE = re.compile(r"\bon[a-zA-Z]+\s*=")


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: Path | str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def write_json(path: Path | str, data: Any, indent: int = 2) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=indent) + "\n")


def strip_code_fence(text: str) -> str:
    """去掉模型可能包的 ```svg / ```json 围栏。"""
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    # drop first fence
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # drop last fence
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_svg(text: str) -> str:
    s = strip_code_fence(text)
    m = re.search(r"(<svg\b[\s\S]*?</svg>)", s, re.I)
    if m:
        return m.group(1).strip()
    return s


def extract_json_obj(text: str) -> Any:
    s = strip_code_fence(text)
    # try whole
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # find first { ... }
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return json.loads(s[start : end + 1])
    raise ValueError("无法从模型输出中解析 JSON 对象")


def parse_animation_decl(value: str) -> tuple[Optional[dict], Optional[str]]:
    """返回 (parsed, error)。"""
    v = (value or "").strip()
    m = _ANIM_RE.match(v)
    if not m:
        return None, f"动画声明格式非法: {value!r}（期望: 动画名 时长 缓动 次数）"
    name = m.group("name").lower()
    if name not in ANIMATION_WHITELIST:
        return None, f"动画名不在白名单: {name}"
    easing = m.group("easing").lower()
    if easing not in EASINGS:
        return None, f"缓动不支持: {easing}"
    return (
        {
            "name": name,
            "duration": m.group("duration"),
            "easing": easing,
            "iters": m.group("iters"),
        },
        None,
    )


def expand_part_keys(key: str) -> list[str]:
    return [p.strip() for p in key.split(",") if p.strip()]


def list_part_ids_from_svg(svg_text: str) -> list[str]:
    """粗提取 g[id]（不校验合法性，仅供上下文）。"""
    ids = re.findall(r'<g\b[^>]*\bid\s*=\s*["\']([^"\']+)["\']', svg_text, re.I)
    # de-dup keep order
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def format_errors(errors: list[dict]) -> str:
    lines = []
    for i, e in enumerate(errors, 1):
        where = e.get("where") or e.get("state") or e.get("part") or ""
        rule = e.get("rule") or e.get("code") or "error"
        msg = e.get("message") or e.get("msg") or str(e)
        lines.append(f"{i}. [{rule}] {where}: {msg}" if where else f"{i}. [{rule}] {msg}")
    return "\n".join(lines)


class LLMClientProtocol:
    """可选 LLM 适配：async/sync 均可包装。"""

    def complete(self, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError


def default_llm_complete(system: str, user: str) -> str:
    """默认尝试复用 Symbix 后端 client（同步包装）。

    若环境无 backend / 无 API key，抛出明确错误，方便 mock 注入。
    """
    try:
        import asyncio
        from application.state import symbix_client, provider_registry  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "无法导入 Symbix LLM client。请在 backend 环境运行，或向脚本注入 llm_complete 回调。"
        ) from e

    provider = provider_registry.get_active()
    prompt = user

    async def _run():
        # 临时覆盖 system prompt
        old = getattr(symbix_client, "system_prompt", "")
        symbix_client.system_prompt = system
        try:
            result = await symbix_client.chat(
                user_input=prompt,
                history=[],
                registry=None,
                tools=None,
                override_api_key=provider.api_key or None,
                override_api_base=provider.api_base or None,
                override_model=provider.model or None,
            )
            return (result.get("content") or "").strip()
        finally:
            symbix_client.system_prompt = old

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 嵌套场景：用新 loop 线程不安全，退而求其次
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(lambda: asyncio.run(_run()))
                return fut.result()
        return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())


def with_llm(llm: Optional[Callable[[str, str], str]]) -> Callable[[str, str], str]:
    return llm or default_llm_complete
