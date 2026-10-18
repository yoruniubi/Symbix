"""行级 diff:把 file_op 的 before/after 文本切成 git 风格的行列表。

前端只负责按 type 着色渲染,不在浏览器里算 diff——省一个前端依赖,
且 difflib 的结果可以直接在后端单测。
"""

from __future__ import annotations

import difflib
from typing import Any

# 改动行上下各保留的上下文行数,超过则折叠成 gap(对齐 git diff 的观感)
CONTEXT_LINES = 3

# 单次返回的行数上限,防止 5MB blob 直接把弹窗撑爆
MAX_DIFF_LINES = 2000


def _split(text: str | None) -> list[str]:
    """按行切分;None 视为空文本(新建前 / 删除后都没有内容)。"""
    if not text:
        return []
    return text.splitlines()


def _collapse_context(lines: list[dict[str, Any]], context: int) -> list[dict[str, Any]]:
    """把远离改动的大段未变更行折叠为 gap 标记,只留改动附近的 context 行。"""
    change_idx = [i for i, ln in enumerate(lines) if ln["type"] != "ctx"]
    if not change_idx:
        return lines

    keep: set[int] = set()
    total = len(lines)
    for i in change_idx:
        keep.update(range(max(0, i - context), min(total, i + context + 1)))

    collapsed: list[dict[str, Any]] = []
    prev: int | None = None
    for i, ln in enumerate(lines):
        if i not in keep:
            continue
        if prev is not None and i - prev > 1:
            collapsed.append({"type": "gap", "count": i - prev - 1})
        collapsed.append(ln)
        prev = i
    return collapsed


def build_line_diff(
    before: str | None,
    after: str | None,
    *,
    context: int = CONTEXT_LINES,
    max_lines: int = MAX_DIFF_LINES,
) -> dict[str, Any]:
    """生成行级 diff。

    入参 before/after 为文件改动前/后的完整文本(None = 文件不存在)。
    出参 lines 每项:
      - type: "ctx" 未变更 | "add" 新增 | "del" 删除 | "gap" 折叠占位
      - old_no / new_no: 对应行号(不适用时为 None)
      - text: 行内容(gap 无 text,只有 count)
    """
    old_lines = _split(before)
    new_lines = _split(after)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    lines: list[dict[str, Any]] = []
    old_no = 1
    new_no = 1
    truncated = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                lines.append({"type": "ctx", "old_no": old_no, "new_no": new_no, "text": old_lines[k]})
                old_no += 1
                new_no += 1
        else:
            for k in range(i1, i2):
                lines.append({"type": "del", "old_no": old_no, "new_no": None, "text": old_lines[k]})
                old_no += 1
            for k in range(j1, j2):
                lines.append({"type": "add", "old_no": None, "new_no": new_no, "text": new_lines[k]})
                new_no += 1
        if len(lines) >= max_lines:
            truncated = True
            break

    if truncated:
        lines = lines[:max_lines]

    add_count = sum(1 for ln in lines if ln["type"] == "add")
    del_count = sum(1 for ln in lines if ln["type"] == "del")

    return {
        "lines": _collapse_context(lines, context),
        "add_count": add_count,
        "del_count": del_count,
        "truncated": truncated,
        "context": context,
        "old_total": len(old_lines),
        "new_total": len(new_lines),
    }