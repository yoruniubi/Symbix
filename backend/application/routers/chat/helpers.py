"""共享辅助:交互工具判定、SSE 批处理、checkpoint 发射、工具链消息构建等。

拆分自 chat.py 的公共部分,供 files_api / approve / stream 复用。
"""
import uuid
import json as _json

from application.schemas import ChatRequest
from application.services.memory_ops import format_sse
from Symbix_sdk.model_capabilities import check_vision
from application.state import checkpoint_recorder

# 交互型工具:执行后返回 pending_user_input,需挂起等待用户回答。
# 命中后强制走"提问审批"路径:不发普通 tool_result,发 await_input 事件挂起。
_INTERACTION_TOOLS = {"ask_clarifying_question"}


def _is_interaction_tool(name: str) -> bool:
    return name in _INTERACTION_TOOLS


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
) -> None:
    """一轮结束时发送 round 总结点。"""
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
    # 已 flush 的 tool_call_id → 是否已拿到对应 tool 结果
    for block in steps:
        if block.get("type") == "tool_calls":
            pending_calls = list(block.get("tool_calls") or [])
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
            out.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", "{}"),
                    },
                }],
            })
            out.append({
                "role": "tool",
                "tool_call_id": tr_id,
                "name": block.get("name", ""),
                "content": block.get("content", ""),
            })
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
