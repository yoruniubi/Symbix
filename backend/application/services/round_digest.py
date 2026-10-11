import json
from typing import Any
from Symbix_sdk.checkpoint import get_recorder

# 摘要粒度:只给最近几轮、每轮最多几条。整体控制在千字级,比让模型重读文件便宜得多。
DIGEST_ROUNDS = 3
DIGEST_ITEMS_PER_ROUND = 8
DIGEST_MAX_CHARS = 1200
DIGEST_FETCH_RECORDS = 400
ARGS_MAX_KEYS = 4
ARGS_VALUE_CHARS = 120
RESULT_CHARS = 120
ERROR_CHARS = 200

# 排在前面展示的参数:一眼能看出「动了哪个文件 / 跑了什么命令」
PREFERRED_KEYS = (
    "path", "file_path", "command", "cmd", "query", "url", "pattern", "name",
    "skill", "from", "to", "old_path", "new_path", "op", "timeout",
)


def _one_line(text: Any, limit: int) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + "…"


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        if len(value) > ARGS_VALUE_CHARS:
            return f"<省略 {len(value)} 字符>"
        return _one_line(value, ARGS_VALUE_CHARS)
    if isinstance(value, (dict, list)):
        dumped = json.dumps(value, ensure_ascii=False)
        return dumped if len(dumped) <= ARGS_VALUE_CHARS else f"<{type(value).__name__} {len(dumped)} 字符>"
    return str(value)


def _summarize_args(arguments: Any) -> str:
    """参数摘要:丢掉正文类大字段(写文件的 content 动辄几千字),只留路径/命令这类短字段。"""
    if not isinstance(arguments, dict) or not arguments:
        return ""
    keys = [k for k in PREFERRED_KEYS if k in arguments]
    keys += [k for k in arguments if k not in PREFERRED_KEYS]
    parts: list[str] = []
    for key in keys:
        if len(parts) >= ARGS_MAX_KEYS:
            parts.append(f"…+{len(keys) - len(parts)} 字段")
            break
        parts.append(f"{key}={_format_value(arguments.get(key))}")
    return " ".join(parts)


def _format_outcome(record: dict, payload: dict) -> str:
    status = record.get("status") or "ok"
    if status in ("error", "superseded"):
        detail = _one_line(record.get("error") or payload.get("result_snippet") or "", ERROR_CHARS)
        return f"{status}: {detail}" if detail else status
    snippet = _one_line(payload.get("result_snippet") or "", RESULT_CHARS)
    return f"ok | {snippet}" if snippet else "ok"


def _format_round(recency: int, calls: list[dict], superseded: bool) -> str:
    """recency=0 表示最近一轮。"""
    label = "上一轮" if recency == 0 else f"上 {recency + 1} 轮"
    meta = f"{len(calls)} 次调用"
    if superseded:
        meta += ",已被重试可能未生效"
    lines = [f"· {label}({meta}):"]
    shown = calls[:DIGEST_ITEMS_PER_ROUND]
    for record in shown:
        payload = record.get("payload") or {}
        line = f"  - {payload.get('tool_name') or 'tool'}"
        args = _summarize_args(payload.get("arguments"))
        if args:
            line += f" {args}"
        lines.append(f"{line} → {_format_outcome(record, payload)}")
    if len(calls) > len(shown):
        lines.append(f"  - …另有 {len(calls) - len(shown)} 次调用未列出")
    return "\n".join(lines)


def _group_rounds(records: list[dict]) -> list[tuple[str, list[dict], bool]]:
    """按 round_id 分组,只保留有工具调用的轮次;组内顺序即 seq 顺序。"""
    groups: list[list[Any]] = []
    for record in records:
        if record.get("kind") != "tool_call":
            continue
        round_id = record.get("round_id") or ""
        superseded = record.get("status") == "superseded"
        if groups and groups[-1][0] == round_id:
            groups[-1][1].append(record)
            groups[-1][2] = groups[-1][2] or superseded
        else:
            groups.append([round_id, [record], superseded])
    return [(round_id, calls, superseded) for round_id, calls, superseded in groups]


def build_recent_tool_digest(session_id: str) -> str:
    """把最近几轮的工具调用压成一段紧凑文本;无记录返回空串。

    数据来自 checkpoint_records(每轮每次工具都有 tool_call 记录),不用新表。
    注入位置与 RAG 记忆一致(拼在用户消息前),不动 system 前缀,避免破坏 prompt cache。
    """
    if not session_id:
        return ""
    try:
        records = get_recorder().store.list_recent(
            session_id, limit=DIGEST_FETCH_RECORDS, include_superseded=True
        )
    except Exception as e:
        print(f"[digest] 读取 checkpoint 失败,跳过 (session={session_id[:8]}…): {e}")
        return ""

    groups = _group_rounds(records)
    if not groups:
        return ""

    blocks: list[str] = []
    used = 0
    for recency, (_, calls, superseded) in enumerate(reversed(groups[-DIGEST_ROUNDS:])):
        block = _format_round(recency, calls, superseded)
        if used + len(block) > DIGEST_MAX_CHARS and blocks:
            break
        blocks.append(block)
        used += len(block)
    blocks.reverse()
    header = "[近期工具记录](你之前实际执行过的操作,不要重复执行;需要细节时再读文件确认)"
    return header + "\n" + "\n".join(blocks)
