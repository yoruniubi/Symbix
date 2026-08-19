"""Checkpoint 数据类 — 5 种事件类型。

设计要点：
- 所有 record 共享 5 个公共字段（id / ts / session_id / round_id / seq）方便 SQL 跨类查询。
- 每种 record 额外携带该事件独有的字段（区分用 kind）。
- 所有 JSON 兼容字段（dict / str 都 json.dumps 到 TEXT，pydantic model_dump(mode="json") 安全）。
- before_hash / after_hash 用 sha256 前 12 位（够区分 + 不占空间）。
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    """统一 ISO8601 + UTC，避免本地时区转换把时间戳对不齐的问题。"""
    return datetime.now(timezone.utc).isoformat()


class RecordKind(str, enum.Enum):
    """事件分类。str enum 方便 SQLite 比较与日志可读。"""
    TOOL_CALL = "tool_call"
    FILE_OP = "file_op"
    COMMAND = "command"
    MCP_CALL = "mcp_call"
    ROUND = "round"


class CheckpointRecord(BaseModel):
    """所有事件 record 的公共字段。子类型通过 kind 区分存储/payload。"""
    id: str                                # uuid4 hex，唯一主键
    kind: RecordKind
    ts: str = Field(default_factory=_utc_now_iso)
    session_id: str
    round_id: str                          # 一次 round = user_msg → agent 一轮 tool_calls → final
    seq: int                               # session 内全局递增序号（recorder 维护）

    # 状态（所有类型共用；错误也都写这里）
    status: Literal["ok", "error", "skipped", "superseded"] = "ok"
    error: Optional[str] = None

    # 该 record 的特异化数据（json object）。子类 model_dump 后填这里。
    payload: dict[str, Any] = Field(default_factory=dict)


# ── 各 kind 的 payload schema ──────────────────────────────────────

class ToolCallRecord(BaseModel):
    """native / skill 工具调用。"""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["safe", "medium", "high", "unknown"] = "unknown"
    approved: bool = True                  # 前端是否点击同意；后台跑默认 True（SAFE only）
    result_snippet: str = ""              # 输出前 500 字，避免把巨大 stdout 全塞进库
    result_truncated: bool = False         # 是否被截断


class FileOpRecord(BaseModel):
    """文件操作 — read / write / append / delete / move，及 agent 恢复动作的 restore。"""
    op: Literal["read", "write", "append", "replace", "delete", "move", "create", "restore"]
    path: str
    size_before: Optional[int] = None
    size_after: Optional[int] = None
    hash_before: Optional[str] = None      # sha256[:12]，给后续比对 / 回溯参考
    hash_after: Optional[str] = None
    size_delta: Optional[int] = None       # write 后 -1KB / +1KB，UI 一眼能看出是不是大改
    blob_stored: bool = False              # 是否真的存了可回退的 before/after 内容


class CommandRecord(BaseModel):
    """命令行执行。"""
    cmd: str                               # 完整命令串
    cwd: str = ""
    exit_code: Optional[int] = None
    stdout_tail: str = ""                  # 末 500 字
    stderr_tail: str = ""                   # 末 500 字
    duration_ms: int = 0


class McpCallRecord(BaseModel):
    """MCP server 工具调用。"""
    server_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_snippet: str = ""
    result_truncated: bool = False


class RoundRecord(BaseModel):
    """一轮 user → agent 整流程的总结点。"""
    user_msg_snippet: str = ""              # user 输入的前 200 字
    user_msg_truncated: bool = False
    assistant_text_snippet: str = ""        # 最终 assistant 输出前 200 字
    assistant_truncated: bool = False
    reasoning_snippet: str = ""             # 思考过程前 200 字（可选）
    tool_count: int = 0                     # 这轮用的工具数
    failed_tools: int = 0                   # 失败工具调用数
    duration_ms: int = 0
