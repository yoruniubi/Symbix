"""共享辅助:交互工具判定、SSE 批处理、checkpoint 发射、工具链消息构建等。

拆分自 chat.py 的公共部分,供 files_api / approve / stream 复用。
"""
import asyncio
import uuid
import json as _json

from application.schemas import ChatRequest
from application.services.memory_ops import format_sse
from Symbix_sdk.client import build_tool_result_messages
from Symbix_sdk.model_capabilities import check_vision
from application.state import checkpoint_recorder

# 交互型工具:执行后返回 pending_user_input,需挂起等待用户回答。
# 命中后强制走"提问审批"路径:不发普通 tool_result,发 await_input 事件挂起。
_INTERACTION_TOOLS = {"ask_clarifying_question", "propose_plan"}


# ═══════════════ 只读工具并行批量执行 ═══════════════
# 模型一轮里常一次性发起多个互不依赖的只读调用(读 5 个文件 / 搜 2 个关键词 /
# 抓 2 个网页)。这些工具内部是阻塞式 I/O(磁盘、HTTP),串行 await 只能一个
# 一个等;这里把**连续的**只读调用丢给线程池并发跑。
#
# 只并行「纯只读、无副作用、无需审批」的工具:
#   写入类(edit_file/md_to_*)、终端(open_terminal)、UI 副作用(emit_pet_action)、
#   交互型(ask_clarifying_question)、delegate_*(自身已并行)都不进来,
#   以免打乱审批/提问挂起顺序或让写入与读取互相偷跑。
READ_ONLY_PARALLEL_TOOLS = {
    "read_file",
    "list_files",
    "search_files",
    "search_file_with_name",
    "parse_file",
    "doc_to_markdown",
    "search_online",
    "fetch_webpage",
    "check_agent_status",
    "list_schedule_jobs",
    "search_memories",
}
READ_ONLY_PARALLEL_PREFIXES = ("skill__",)
PARALLEL_TOOL_CONCURRENCY = 6


def _is_read_only_parallel_tool(name: str) -> bool:
    """该工具能不能进并行批量(仅看名字,审批/重复判定由调用方补上)。"""
    if not name or name in _INTERACTION_TOOLS:
        return False
    if name in READ_ONLY_PARALLEL_TOOLS:
        return True
    return name.startswith(READ_ONLY_PARALLEL_PREFIXES)


async def run_tools_parallel(items, concurrency: int = PARALLEL_TOOL_CONCURRENCY):
    """并发执行只读工具,按**完成顺序** yield (index, output_str)。

    Args:
        items: [(index, name, arguments)] —— arguments 可为 dict 或 JSON 字符串
        concurrency: 同时最多几个(避免一次几十个网络请求把上游打爆)
    """
    from application.state import tool_registry

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(index, name, arguments):
        async with sem:
            try:
                # asyncio.to_thread 会带上当前 contextvars(含 checkpoint 的 ctx),
                # 所以工具内部的 _ctx_* 读取与串行路径一致。
                out = await asyncio.to_thread(tool_registry.execute, name, arguments)
            except Exception as e:  # 单个失败不影响同批其它工具
                out = f"[Error] 工具 {name} 执行失败: {e}"
        if not isinstance(out, str):
            out = _json.dumps(out, ensure_ascii=False)
        return index, out

    tasks = [asyncio.create_task(_one(i, n, a)) for i, n, a in items]
    try:
        for fut in asyncio.as_completed(tasks):
            yield await fut
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


def _is_interaction_tool(name: str) -> bool:
    return name in _INTERACTION_TOOLS


# ═══════════════ 工具执行(同步/异步统一入口) ═══════════════
# 绝大多数工具是同步函数;delegate_task(子 Agent 委派)是 async,需 await。
# 这里统一封装,避免每个执行点都写 if/await 分支。

async def _execute_tool(name: str, arguments, ctx: dict | None = None, on_event=None) -> str:
    """执行工具并保证返回 str。异步工具(delegate_task)走 await,其余同步。

    Args:
        name: 工具名
        arguments: 参数(dict/JSON 字符串)
        ctx: 请求级上下文(api_key/api_base/model),透传给异步工具
        on_event: 可选异步进度回调,透传给异步工具
    """
    from application.state import tool_registry

    if tool_registry.is_async_tool(name):
        out = await tool_registry.execute_async(name, arguments, on_event=on_event, ctx=ctx)
    else:
        out = tool_registry.execute(name, arguments)
    if not isinstance(out, str):
        out = _json.dumps(out, ensure_ascii=False)
    return out


async def _stream_tool_events(name: str, arguments, ctx: dict | None = None):
    """执行工具;若是异步工具,期间把进度事件 yield 出来。

    产出元组:
      ("progress", event_dict) —— 子 Agent 进度(仅异步工具会有)
      ("result", str)          —— 最终工具结果(始终是最后一项)
    """
    from application.state import tool_registry

    if not tool_registry.is_async_tool(name):
        out = tool_registry.execute(name, arguments)
        yield ("result", out if isinstance(out, str) else _json.dumps(out, ensure_ascii=False))
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def _on_event(ev: dict) -> None:
        await queue.put(ev)

    task = asyncio.create_task(
        tool_registry.execute_async(name, arguments, on_event=_on_event, ctx=ctx)
    )
    while not task.done():
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.25)
            yield ("progress", ev)
        except asyncio.TimeoutError:
            continue
    # 收尾:排空剩余进度,再取最终结果
    while not queue.empty():
        yield ("progress", queue.get_nowait())
    out = await task
    yield ("result", out if isinstance(out, str) else _json.dumps(out, ensure_ascii=False))


def _parse_interaction_request(tool_output: str) -> dict | None:
    """解析交互型工具的返回 JSON,失败或非 pending 状态返回 None。"""
    if not isinstance(tool_output, str) or not tool_output.strip().startswith("{"):
        return None
    try:
        data = _json.loads(tool_output)
    except Exception:
        return None
    if data.get("status") != "pending_user_input":
        return None
    return data


# 为避免上游 模型逐 token 推 delta 导致前端 高频解析/rAF 重绘，这里将连续 delta 事件批量合并
class _DeltaBatcher:
    """攒批 delta 事件：相邻 delta 合并到默认 彈；遇非 delta 或达上限立即 flush。"""
    def __init__(self, max_chunks: int = 1, max_chars: int = 8) -> None:
        # 阈值已降至近实时转发（来一个 delta 即 flush），
        # 仅保留结构以备极端高频场景下做轻度节流。
        self.max_chunks = max_chunks
        self.max_chars = max_chars
        self._buf = ""
        self._n = 0
        self._has = False

    def add_delta(self, s: str) -> dict | None:
        """加入 delta，返回 flush 事件（若需）或 None仍需继续攒。"""
        if not s:
            return None
        self._buf += s
        self._n += 1
        self._has = True
        if self._n >= self.max_chunks or len(self._buf) >= self.max_chars:
            return self.flush()
        return None

    def flush(self) -> dict | None:
        if not self._has:
            return None
        evt = {"type": "delta", "content": self._buf}
        self._buf = ""
        self._n = 0
        self._has = False
        return evt


def _batch_yield(
    event: dict,
    batcher: "_DeltaBatcher",
    on_delta: "callable[[str], None] | None" = None,
):
    """对单个上游事件，返回需 yield 的 SSE 字符串列表（顺序：先 flush缓冲 delta，再透传本事件）。"""
    out: list[str] = []
    etype = event.get("type")
    if etype == "delta":
        content = event.get("content", "")
        if on_delta is not None:
            on_delta(content)
        flushed = batcher.add_delta(content)
        if flushed is not None:
            out.append(format_sse(flushed))
        return out
    # 非 delta：先 flush 缓冲，再透传
    flushed = batcher.flush()
    if flushed is not None:
        out.append(format_sse(flushed))
    out.append(format_sse(event))
    return out


def _new_round_id() -> str:
    """生成一轮 user_msg → agent 的 round 标识。"""
    return uuid.uuid4().hex[:12]


def _emit_tool(
    session_id: str,
    round_id: str,
    tc_name: str,
    tc_args,
    risk_level,
    approved: bool,
    tool_output: str,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """统一处理 tool_call 的 checkpoint 发射。"""
    try:
        args_dict = (
            _json.loads(tc_args) if isinstance(tc_args, str) and tc_args else
            (tc_args if isinstance(tc_args, dict) else {})
        )
    except Exception:
        args_dict = {"_raw": str(tc_args)}
    # risk_level 可能是 ToolRiskLevel 枚举或 str
    rl = str(risk_level).split(".")[-1].lower() if risk_level else "unknown"
    try:
        checkpoint_recorder.emit_tool_call(
            session_id=session_id,
            round_id=round_id,
            tool_name=tc_name,
            arguments=args_dict,
            risk_level=rl,
            approved=approved,
            status=status,
            error=error,
            result_snippet=tool_output or "",
        )
    except Exception as e:
        print(f"[checkpoint] emit_tool_call failed: {e}")


def _emit_round_summary(
    session_id: str,
    round_id: str,
    user_msg: str,
    assistant_text: str,
    reasoning: str | None,
    tool_count: int,
    failed_tools: int,
    duration_ms: int = 0,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """一轮结束时发送 round 总结点(status=error 用于中断/异常轮)。"""
    try:
        checkpoint_recorder.emit_round(
            session_id=session_id,
            round_id=round_id,
            user_msg=user_msg or "",
            assistant_text=assistant_text or "",
            reasoning=reasoning or "",
            tool_count=tool_count,
            failed_tools=failed_tools,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )
    except Exception as e:
        print(f"[checkpoint] emit_round failed: {e}")

# ═══════════════ 工具链消息辅助(多轮工具上下文累积用) ═══════════════
# 背景:早期实现里,agent 每轮工具循环都用固定的 history 重建 msgs,
# 只拼当前轮的 tool_calls + tool 结果 → 前几轮已执行的工具对模型不可见,
# 模型会"失忆"而反复调用同一工具(尤其审批打断后更严重)。
# 修复思路:整轮 agent 循环内维护一个持续增长的 running_msgs,
# 每轮把本轮的 assistant(tool_calls) + tool 结果 append 进去,
# 让模型始终能看到"已调过什么、结果是什么"。

# 累积工具结果达到该估算 token 上限时,终止工具循环并给兑底提示。
# 无 tiktoken,用近似估算:中文字符 ≈ 1.5 token,其他字符 ≈ 0.3 token。
MAX_CUM_TOOL_TOKENS = 120_000


def _estimate_tool_tokens(text: str) -> int:
    """粗略估算一段文本占用的 token 数(无 tiktoken 时的近似值)。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk * 1.5 + other * 0.3)


def _steps_to_tool_messages(steps: list[dict]) -> list[dict]:
    """从 steps 中提取"已执行"的工具链,转成 OpenAI 消息序列。

    steps 由若干 round 块组成:开头一条 {"type":"tool_calls","tool_calls":[{id,name,arguments}]},
    其后紧跟每条已执行工具对应的 {"type":"tool_result",tool_call_id,name,content}。
    被审批拦下/无结果的 tool_call(悬空)不算已执行,剔除。

    返回的 messages 结构:
      assistant(带 tool_calls)  →  tool(tool_call_id...)  →  assistant(带 tool_calls)  →  ...
    供审批续跑/多轮累积时 extend 回 running_msgs,保证模型能看到审批前已经跑过的工具。
    """
    out: list[dict] = []
    # 当前正在累积的 round 的 tool_calls(尚未 flush 成 assistant 消息)
    pending_calls: list[dict] = []
    # 该 round 的思考内容:思考模式的上游要求回传,否则续跑会 400
    pending_reasoning: str | None = None
    # 已 flush 的 tool_call_id → 是否已拿到对应 tool 结果
    for block in steps:
        if block.get("type") == "tool_calls":
            pending_calls = list(block.get("tool_calls") or [])
            pending_reasoning = block.get("reasoning") or None
            continue
        if block.get("type") == "tool_result":
            tr_id = block.get("tool_call_id")
            # 只有带结果且确实执行过(approved 不为 False / 拒绝)的才算已执行
            if block.get("approved") is False:
                continue
            # 找到 pending_calls 中对应的调用,组成一对
            tc = next((c for c in pending_calls if c.get("id") == tr_id), None)
            if tc is None:
                continue
            build_tool_result_messages(out, [{
                "tool_call_id": tc["id"],
                "name": tc.get("name", ""),
                "arguments": tc.get("arguments", "{}") or "{}",
                "content": block.get("content", ""),
            }], reasoning=pending_reasoning)
    return out


def _assert_tool_pairing(messages: list[dict], strict: bool = False) -> None:
    """校验 messages 里每个 assistant.tool_calls 的 id 是否都能在后续 tool 消息找到配对。

    strict=True(开发/单测)时断言失败直接抛错;False(生产)只记日志,避免校验本身
    变成新的稳定性风险点。
    """
    expect_ids: list[str] = []  # 尚未配对的 tool_call id
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            expect_ids.extend(tc["id"] for tc in m["tool_calls"])
        elif role == "tool":
            tid = m.get("tool_call_id")
            if tid in expect_ids:
                expect_ids.remove(tid)
    if expect_ids:
        msg = f"[tool pairing] 存在未配对的 tool_call_id: {expect_ids}"
        if strict:
            raise AssertionError(msg)
        print(msg)


def _prepare_user_message(
    request: ChatRequest,
) -> tuple[str, list[dict], list[dict]]:
    """
    解析 attachments 并注入用户消息；返回 (enriched_text, parsed_list, image_parts)。

    注意：本函数不做视觉能力检测，始终返回 image_parts。
    视觉能力检测是异步操作，需在调用点用 check_vision() 完成。
    """
    from Symbix_sdk.tools.file_pipeline import inject_attachments_into_message

    atts = []
    for a in request.attachments or []:
        if hasattr(a, "model_dump"):
            atts.append(a.model_dump())
        elif isinstance(a, dict):
            atts.append(a)
        else:
            atts.append(dict(a))

    enriched, parsed_list, image_parts = inject_attachments_into_message(
        request.message, atts
    )
    return enriched, parsed_list, image_parts


def attachment_history_note(parsed_atts: list[dict]) -> str:
    """
    把附件摘要(尤其是参考图的尺寸/主色)拼成一行,写进会话记忆。

    图像只在当轮上传时传入,所以无视觉模型、以及后续轮次(「请继续」)
    只能靠这段文字拿到参考图信息——不写进历史,模型就会去翻文件、开浏览器找图。
    """
    parts = [
        str(p.get("image_summary", "")).strip()
        for p in parsed_atts or []
        if isinstance(p, dict) and p.get("image_summary")
    ]
    return "\n".join(p for p in parts if p)


async def _filter_image_parts(
    image_parts: list[dict],
    model: str,
    api_key: str,
    api_base: str,
) -> tuple[list[dict], bool]:
    """
    探测模型视觉能力并返回 (image_parts, supports_vision)。

    不再把 image_parts 清空——无视觉模型时由 client._build_messages 内部
    降级为"取色 + 文本描述"(提取参考图主色拼进 prompt),让 skill 生成
    SVG 时颜色能贴合参考图。有视觉时保留多模态 image_parts。
    """
    if not image_parts:
        return image_parts, False
    supports = await check_vision(model, api_key, api_base)
    if not supports:
        print(f"[chat] 模型 {model} 不支持视觉,{len(image_parts)} 张图片降级为取色+文本描述")
    return image_parts, supports
