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
            else:
                # 这轮没有任何工具调用 —— 可能是纯对话,也可能是上游 429/鉴权
                # 在第一枪就把流掐断了。后者必须进时间线:否则模型完全不知道
                # 「刚才试过、失败了」,只会从头再走一遍,表现就是拖沓。
                groups.append([round_id, [], False, record])
                index[round_id] = len(groups) - 1
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
    # 只保留「做过事」或「失败了」的轮次:纯聊天轮(ok 且零工具)不该占时间线
    out: list[tuple[str, list[dict], bool, Any]] = []
    for rid, calls, sup, note in groups:
        if calls or (note is not None and (note.get("status") or "ok") != "ok"):
            out.append((rid, calls, sup, note))
    return out


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

# ═══════════════════════════════════════════════════════════════════
# 任务进度总览
#
# 上面的「近期工具记录」只带最近 DIGEST_ROUNDS 轮 —— 轮次一长,前面干了什么
# 就彻底看不到了;会话压缩又只留 200 字摘要(还不含工具细节)。于是 429/断线
# 之后模型再接手时,对「这个任务做到哪一步」是空白的,只能从头探索一遍。
#
# 这一段不分轮次,把整个会话的动作按「读过/改过/跑过/失败过」去重聚合成几行,
# 无论从哪续上都能看到全局。
# ═══════════════════════════════════════════════════════════════════

PROGRESS_MAX_CHARS = 420
PROGRESS_MAX_PER_KIND = 6
PROGRESS_FETCH_RECORDS = 400

PROGRESS_HEADER = (
    "[本次任务进度](整个会话累计,不是只看最近几轮;"
    "续跑前先看这里,确认做到哪一步,别从头再来一遍)"
)

_READ_TOOLS = frozenset({
    "read_file", "read", "list_dir", "list_files", "list_directory",
    "read_many", "read_office", "ocr_image", "read_excel", "read_docx", "read_pdf",
})
# 搜索类单独归类:它们的「操作对象」是搜的那个词,不是搜索范围 ——
# 把 D:/proj 显示成 proj 对模型没有任何信息量。
_SEARCH_TOOLS = frozenset({"grep", "search_files", "search_in_files"})
_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "replace_in_file", "create_file", "apply_patch",
    "delete_file", "move_file", "copy_file", "write_office", "make_dir",
})
_RUN_TOOLS = frozenset({
    "open_terminal", "run_command", "execute_command", "run_script",
    "run_python", "run_node",
})

_PATH_KEYS = ("path", "file_path", "old_path", "new_path", "target", "from", "to")
_CMD_KEYS = ("command", "cmd", "script", "code")
_QUERY_KEYS = ("query", "pattern", "keyword", "url")


def _pick_target(args: dict, keys: tuple[str, ...]) -> str:
    """从工具参数里挑出最能代表「操作对象」的那个值。"""
    if not isinstance(args, dict):
        return ""
    for k in keys:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _short_name(text: str, limit: int = 28) -> str:
    """路径取文件名,命令取首行;超长截断 —— 总览里不铺开细节。"""
    text = (text or "").strip().splitlines()[0] if text else ""
    # 同时兼容 Windows 与 POSIX 分隔符(记录里两种都出现过)
    base = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or text
    return base if len(base) <= limit else base[: limit - 1] + "…"


# 工具输出落库时的截断长度:够模型判断「这一步拿到了什么」,
# 又不至于让 memory.db 膨胀。失败的输出往往最有用,所以给得比摘要宽松些。
TOOL_MEMO_RESULT_CHARS = 500
TOOL_MEMO_MAX_CHARS = 3000


def format_tool_memo(round_no: int, results: list[dict],
                     max_chars: int = TOOL_MEMO_MAX_CHARS) -> str:
    """把一轮的工具执行结果压成一条可落库的 memo。

    一轮压成一条(而不是一个工具一条):40 轮 × 3 工具 = 120 条会把
    messages 表撑爆,也会让缩略窗口里全是 tool、对话只剩几条。

    Args:
        round_no: 第几轮(从 1 起)
        results: [{name, arguments(JSON 字符串), content(工具输出)}]
        max_chars: 单条 memo 上限

    Returns:
        role="tool" 消息的 content;没有可用结果时返回空串
    """
    if not results:
        return ""
    parts: list[str] = []
    for item in results:
        name = (item.get("name") or "tool").strip()
        raw_args = item.get("arguments")
        args: dict = {}
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except Exception:
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        # 路径要给全:只留 basename 的话 D:/a/server.py 和 D:/b/server.py
        # 会混成同一个,续跑时看到「读过 server.py」等于没说。
        # _QUERY_KEYS 兜底是为了 grep/search 这类工具能显示搜索词而非空壳。
        target = (_pick_target(args, _PATH_KEYS)
                  or _pick_target(args, _CMD_KEYS)
                  or _pick_target(args, _QUERY_KEYS))
        head = f"{name}({target[:80]})" if target else name
        out = (item.get("content") or "").strip()
        snippet = _one_line(out, TOOL_MEMO_RESULT_CHARS)
        total = len(out)
        # 标注原始长度:模型据此判断「这个文件很大,需要分段读」还是「就几行」
        tail = f"…(共 {total} 字符)" if total > TOOL_MEMO_RESULT_CHARS else ""
        parts.append(f"{head} → {snippet}{tail}" if snippet else f"{head} → (空输出)")

    text = f"[第{round_no}轮工具] " + "; ".join(parts)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def extract_file_ops(session_id: str, limit: int = 30) -> dict[str, list[str]]:
    """从 checkpoint 里抽出本会话「读过 / 改过」的文件全量清单。

    数据源是 checkpoint_records,独立于会话压缩 —— 长任务跨多少次压缩都不会丢,
    所以每次现算即可,不需要像 pi 那样把清单在摘要之间累积传递。

    Args:
        session_id: 会话 id
        limit: 每类最多列几个

    Returns:
        {"read": [...], "modified": [...]}，路径去重且保序;无记录返回空列表
    """
    out: dict[str, list[str]] = {"read": [], "modified": []}
    if not session_id:
        return out
    try:
        records = get_recorder().store.list_recent(
            session_id, limit=PROGRESS_FETCH_RECORDS, include_superseded=True
        )
    except Exception:
        return out

    seen: dict[str, set[str]] = {"read": set(), "modified": set()}

    def _add(bucket: str, path: str) -> None:
        if not path or path in seen[bucket] or len(out[bucket]) >= limit:
            return
        seen[bucket].add(path)
        out[bucket].append(path)

    for record in records:
        if record.get("kind") != "tool_call":
            continue
        payload = record.get("payload") or {}
        name = (payload.get("tool_name") or "").strip()
        args = payload.get("arguments") or {}
        if name in _WRITE_TOOLS:
            _add("modified", _pick_target(args, ("path", "file_path", "new_path", "target", "to")))
            # 改之前往往读过一次,顺手也记进读过(edit 的 old_path 就是原文件)
            _add("read", _pick_target(args, ("old_path", "file_path", "path")))
        elif name in _READ_TOOLS:
            _add("read", _pick_target(args, _PATH_KEYS))
    return out


def format_file_ops_block(ops: dict[str, list[str]], max_chars: int = 900) -> str:
    """把文件清单排成 pi 那种 <read-files> / <modified-files> 块。"""
    read = ops.get("read") or []
    modified = ops.get("modified") or []
    if not read and not modified:
        return ""
    parts: list[str] = []
    if read:
        parts.append("<read-files>\n" + "\n".join(read) + "\n</read-files>")
    if modified:
        parts.append("<modified-files>\n" + "\n".join(modified) + "\n</modified-files>")
    text = "\n".join(parts)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def build_task_progress(session_id: str, max_chars: int = PROGRESS_MAX_CHARS) -> str:
    """把整个会话的动作聚合成一段「做到哪一步」的总览;轮次太少时返回空串。

    Args:
        session_id: 会话 id
        max_chars: 总长上限

    Returns:
        可直接拼进用户消息的文本;只有一轮或读不到记录时返回空串
    """
    if not session_id:
        return ""
    try:
        records = get_recorder().store.list_recent(
            session_id, limit=PROGRESS_FETCH_RECORDS, include_superseded=True
        )
    except Exception:
        return ""

    groups = _collect_rounds(records)
    # 只有一轮时,近期工具记录已经把它说全了,再来一段总览纯属重复占字数
    if len(groups) < 2:
        return ""

    read: list[str] = []
    wrote: list[str] = []
    ran: list[str] = []
    ran_fail: dict[str, int] = {}
    err_kinds: dict[str, int] = {}

    def _add(bucket: list[str], item: str) -> None:
        if item and item not in bucket:
            bucket.append(item)

    for _, calls, _, note in groups:
        for rec in calls:
            payload = rec.get("payload") or {}
            name = (payload.get("tool_name") or "").strip()
            args = payload.get("arguments") or {}
            ok = bool(payload.get("ok"))
            if name in _SEARCH_TOOLS:
                _add(read, _short_name(_pick_target(args, _QUERY_KEYS) or _pick_target(args, _PATH_KEYS)))
            elif name in _READ_TOOLS:
                _add(read, _short_name(_pick_target(args, _PATH_KEYS + _QUERY_KEYS)))
            elif name in _WRITE_TOOLS:
                _add(wrote, _short_name(_pick_target(args, _PATH_KEYS)))
            elif name in _RUN_TOOLS:
                cmd = _short_name(_pick_target(args, _CMD_KEYS))
                _add(ran, cmd)
                if not ok and cmd:
                    ran_fail[cmd] = ran_fail.get(cmd, 0) + 1
        # 轮级失败:429 限流 / 鉴权 / 5xx 各记一次,让模型知道「不是我写错了,是上游挂了」
        status = (note or {}).get("status") or "ok"
        if status != "ok":
            err = (note or {}).get("error") or status
            kind = "429 限流" if "429" in err else ("鉴权失败" if "401" in err or "403" in err else _short_name(err, 24))
            err_kinds[kind] = err_kinds.get(kind, 0) + 1

    lines: list[str] = []
    if read:
        lines.append(_fmt_line("读过", read, "个"))
    if wrote:
        lines.append(_fmt_line("改过", wrote, "个"))
    if ran:
        shown = [f"{c}(失败 {ran_fail[c]} 次)" if c in ran_fail else c for c in ran]
        lines.append(_fmt_line("跑过", shown, "条"))
    if err_kinds:
        lines.append("- 失败过: " + ", ".join(f"{k}×{v}" for k, v in err_kinds.items()))

    if not lines:
        return ""
    out = PROGRESS_HEADER + "\n" + "\n".join(lines)
    if len(out) <= max_chars:
        return out
    # 超长就砍到上限(总览只是索引,细节仍靠上面的近期记录)
    return out[: max_chars - 1] + "…"


def _fmt_line(label: str, items: list[str], suffix: str) -> str:
    total = len(items)
    shown = items[:PROGRESS_MAX_PER_KIND]
    more = total - len(shown)
    body = ", ".join(shown) + (f" 等 {total} {suffix}" if more else "")
    return f"- {label} {total} {suffix}: {body}"
