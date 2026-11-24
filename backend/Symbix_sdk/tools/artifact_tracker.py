from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from Symbix_sdk.tools.file_pipeline import session_upload_dir, workspace_roots

# 依赖 / 缓存 / 构建产物目录:里面的文件不是用户要的东西,且数量极大。
_PRUNED_DIRS = frozenset({
    "node_modules",
    ".git",
    "__pycache__",
    "site-packages",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    ".next",
    ".nuxt",
    ".gradle",
    ".idea",
    ".vscode",
    "target",
    "obj",
})

# 单次扫描的文件数上限。工作区授权到超大目录(如整个 D:)时,没有上限会
# 让每轮对话多花几秒。超限就少记一些 —— 产物卡漏列比整轮变卡好。
MAX_SCAN_FILES = 6000

# 目录递归深度上限,防止软链接环 / 超深目录树。
MAX_DEPTH = 12

# 快照结构:绝对路径(normcase) -> (mtime_ns, size)
Snapshot = Dict[str, tuple]


def _scan_roots(session_id: str) -> List[str]:
    """本轮要监听的目录。去重后保序。"""
    roots: List[str] = []
    seen = set()
    try:
        roots.append(session_upload_dir(session_id))
    except Exception:
        pass
    try:
        roots.extend(workspace_roots())
    except Exception:
        pass
    out: List[str] = []
    for r in roots:
        if not r:
            continue
        try:
            p = os.path.normcase(os.path.abspath(r))
        except Exception:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(r)
    return out


def _walk(root: str, out: Dict[str, tuple], budget: List[int]) -> None:
    """把 root 下所有普通文件塞进 out,超预算立即停手。"""
    base_depth = root.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if budget[0] <= 0:
            return
        # 就地裁剪,os.walk 不会再进这些目录
        dirnames[:] = [d for d in dirnames if d.lower() not in _PRUNED_DIRS]
        depth = dirpath.count(os.sep) - base_depth
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        for name in filenames:
            if budget[0] <= 0:
                return
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if not os.path.isfile(full):
                continue
            key = os.path.normcase(os.path.abspath(full))
            out[key] = (st.st_mtime_ns, st.st_size)
            budget[0] -= 1


def snapshot(session_id: str) -> Dict[str, tuple]:
    """拍一张当前磁盘快照。失败(路径不存在等)时安静返回已拿到的部分。"""
    snap: Dict[str, tuple] = {}
    budget = [MAX_SCAN_FILES]
    for root in _scan_roots(session_id):
        if not os.path.isdir(root):
            continue
        try:
            _walk(root, snap, budget)
        except Exception:
            continue
        if budget[0] <= 0:
            break
    return snap


def _op_for(before: Optional[tuple], after: Optional[tuple]) -> str:
    if before is None:
        return "create"
    if after is None:
        return "delete"
    return "edit"


def diff_snapshots(before: Dict[str, tuple], after: Dict[str, tuple]) -> List[Dict[str, Any]]:
    """比对两张快照,返回变更列表(按路径排序,结果稳定便于测试)。

    只报「新增 / 修改 / 删除」三种。内容没变但被 touch 过的文件(仅 mtime
    变化、大小一致)也算修改 —— 重写同名同长度的文件确实发生了写入,报出来
    比漏掉安全。
    """
    changes: List[Dict[str, Any]] = []
    for key, cur in after.items():
        prev = before.get(key)
        if prev == cur:
            continue
        if prev is not None and prev[0] == cur[0] and prev[1] == cur[1]:
            continue
        changes.append({
            "path": key,
            "op": _op_for(prev, cur),
            "size": cur[1],
        })
    for key, prev in before.items():
        if key in after:
            continue
        changes.append({
            "path": key,
            "op": "delete",
            "size": prev[1],
        })
    changes.sort(key=lambda c: c["path"])
    return changes


def round_file_changes(session_id: str, before: Dict[str, tuple]) -> List[Dict[str, Any]]:
    """轮末调用:现拍一张快照,与轮初的对比。"""
    return diff_snapshots(before, snapshot(session_id))
