"""Agent 行为 Checkpoint 模块 — 记录 Agent 一次任务中所有动了什么、方便回溯。

核心定位：与 memory（对话文本）正交的另一条数据线——「外部副作用流水」。
- 只记对外部世界产生了影响的操作：工具调用 / 文件修改 / 命令执行 / MCP 调用。
- 不记纯推理 token、不记 LLM 内部思考。
- 单 session 一份隐式时间线，按 (round_id, seq) 顺序追加。
- 用户开 UI 时通过 `/sessions/{id}/timeline` 回溯。
"""
from .recorder import CheckpointRecorder, get_recorder, init_recorder
from .schema import (
    CheckpointRecord,
    ToolCallRecord,
    FileOpRecord,
    CommandRecord,
    McpCallRecord,
    RoundRecord,
    RecordKind,
)

__all__ = [
    "CheckpointRecorder",
    "get_recorder",
    "CheckpointRecord",
    "ToolCallRecord",
    "FileOpRecord",
    "CommandRecord",
    "McpCallRecord",
    "RoundRecord",
    "RecordKind",
]
