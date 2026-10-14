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

# 轮次结论行单独限长:结论是模型自己写的,可能啰嗦,只留一句
ROUND_NOTE_CHARS = 100

# 排在前面展示的参数:一眼能看出「动了哪个文件 / 跑了什么命令」
PREFERRED_KEYS = (
    "path", "file_path", "command", "cmd", "query", "url", "pattern", "name",
    "skill", "from", "to", "old_path", "new_path", "op", "timeout",
)


def _one_line(text: Any, limit: int) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + "..."


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
            parts.append(f"...+{len(keys) - len(parts)} 字段")
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


def _format_round_note(round_rec: dict, calls: list[dict]) -> str:
    """轮次结论行:这一轮整体成不成。

    工具行只说明「调过什么」,说不出「这轮到底做完了没有 / 为什么失败」;
    而 round 记录里正好有 status / failed_tools / duration,恰好补上这一层。
    模型看不到它,就容易重复踩同一个坑(比如上游报错后原样再试一遍)。
    """
    payload = round_rec.get("payload") or {}
    bits: list[str] = []
    status = round_rec.get("status") or "ok"
    if status != "ok":
        detail = _one_line(round_rec.get("error") or "", ROUND_NOTE_CHARS)
        bits.append(f"{status}: {detail}" if detail else status)
    failed = int(payload.get("failed_tools") or 0)
    if failed:
        bits.append(f"其中 {failed} 次工具失败")
    duration_ms = int(payload.get("duration_ms") or 0)
    if duration_ms >= 1000:
        bits.append(f"耗时 {duration_ms / 1000:.1f}s")
    if not bits:
        # 一切正常时也给一条结论:断言「这轮已完成」,避免模型以为还需要收尾
        if not calls:
            return ""
        bits.append("已完成")
    return "  ↳ 结论: " + ",".join(bits)


def _format_round(recency: int, calls: list[dict], superseded: bool,
                  round_rec: dict | None = None) -> str:
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
        lines.append(f"  - ...另有 {len(calls) - len(shown)} 次调用未列出")
    if round_rec:
        note = _format_round_note(round_rec, calls)
        if note:
            lines.append(note)
    return "\n".join(lines)


def _collect_rounds(records: list[dict]) -> list[tuple[str, list[dict], bool, dict | None]]:
    """按 round_id 分组,只保留有工具调用的轮次;组内顺序即 seq 顺序。

    同时把该轮末尾的 round 总结点(kind="round")挂上来 —— 它带有这一轮的整体结论。
    """
    groups: list[list[Any]] = []
    index: dict[str, int] = {}
    for record in records:
        kind = record.get("kind")
        round_id = record.get("round_id") or ""
        if kind == "round":
            # 轮次总结点:挂到对应分组(该轮的 tool_call 一定在前面)
            pos = index.get(round_id)
            if pos is not None:
                groups[pos][3] = record
            continue
        if kind != "tool_call":
            continue
        superseded = record.get("status") == "superseded"
        if groups and groups[-1][0] == round_id:
            groups[-1][1].append(record)
            groups[-1][2] = groups[-1][2] or superseded
        else:
            groups.append([round_id, [record], superseded, None])
            index[round_id] = len(groups) - 1
    return [(rid, calls, sup, note) for rid, calls, sup, note in groups]


# 默认表头:给主 Agent 自己看
DIGEST_HEADER = "[近期工具记录](你之前实际执行过的操作,不要重复执行;需要细节时再读文件确认)"
# 子 Agent 用的表头:那些操作是「主 Agent」做的,不是它自己做的
CHILD_DIGEST_HEADER = (
    "[主链路近期操作](这些是主 Agent 在你之前已经做过的操作,不要重复执行;"
    "需要细节时再读文件确认,只补它没覆盖到的部分)"
)
# 子 Agent 上下文更紧,只带最近 2 轮
CHILD_DIGEST_ROUNDS = 2


def build_recent_tool_digest(session_id: str, header: str = DIGEST_HEADER,
                             rounds: int = DIGEST_ROUNDS,
                             max_chars: int = DIGEST_MAX_CHARS) -> str:
    """把最近几轮的工具调用压成一段紧凑文本;无记录返回空串。

    数据来自 checkpoint_records(每轮每次工具都有 tool_call 记录),不用新表。
    注入位置与 RAG 记忆一致(拼在用户消息前),不动 system 前缀,避免破坏 prompt cache。

    Args:
        session_id: 会话 id
        header: 表头(子 Agent 场景换一份措辞,见 CHILD_DIGEST_HEADER)
        rounds: 最多带几轮(子 Agent 用 CHILD_DIGEST_ROUNDS 压得更短)
        max_chars: 总长上限

    Returns:
        可直接拼进用户消息的文本;无记录返回空串
    """
    if not session_id:
        return ""
    rounds = max(1, rounds)
    try:
        records = get_recorder().store.list_recent(
            session_id, limit=DIGEST_FETCH_RECORDS, include_superseded=True
        )
    except Exception as e:
        print(f"[digest] 读取 checkpoint 失败,跳过 (session={session_id[:8]}...): {e}")
        return ""

    groups = _collect_rounds(records)
    if not groups:
        return ""

    blocks: list[str] = []
    used = 0
    for recency, (_, calls, superseded, round_rec) in enumerate(reversed(groups[-rounds:])):
        block = _format_round(recency, calls, superseded, round_rec)
        if used + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        used += len(block)
    blocks.reverse()
    return header + "\n" + "\n".join(blocks)