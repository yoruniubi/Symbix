"""BlobStore — 文件内容快照存储（Checkpoint 可回退的基础）。

- 存内容不可变的文件快照，用 sha256 前 12 位作文件名做内容寻址去重。
- 目录：与 memory.db 同级的 `checkpoint_blobs/`。
- 只存文本内容（调用方负责判断是否为文本文件）；单文件上限 5MB，超限不存只记 hash。
- 线程安全：目录操作 + 单文件写，靠内容寻址天然幂等（同内容同 hash，写多少次都一份）。
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional


# 单文件内容上限：超过则不落盘 blob，只让上层记 hash（emit 时 blob_stored=False）。
MAX_BLOB_BYTES = 5 * 1024 * 1024


class BlobStore:
    def __init__(self, blob_dir: str):
        """blob_dir 为 checkpoint_blobs 目录绝对路径。"""
        self.blob_dir = blob_dir
        os.makedirs(blob_dir, exist_ok=True)

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    def put(self, content: str) -> str:
        """写入内容，返回 hash（前 12 位）。同内容已存在则跳过（去重）。

        返回的 hash 即使内容超限也返回（仅不落盘，见 out_of_range 语义：
        由调用方判断 `get` 拿不到时按未存储处理）。
        """
        h = self._hash(content)
        # 超限内容不落盘，但 hash 仍返回给上层做 `blob_stored=False` 标记。
        if len(content.encode("utf-8")) > MAX_BLOB_BYTES:
            return h
        path = self._path(h)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            pass  # 已存在（内容寻址去重），无需重写
        return h

    def get(self, hash: str) -> Optional[str]:
        """按 hash 读内容。不存在返回 None。"""
        path = self._path(hash)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def exists(self, hash: str) -> bool:
        return os.path.exists(self._path(hash))

    def delete(self, hash: str) -> None:
        """删除单个 blob。文件不存在时不报错。"""
        path = self._path(hash)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def list_all_hashes(self) -> set[str]:
        """扫描目录里所有 blob 文件名（不含 .json 等；此处纯内容文件无扩展名）。"""
        try:
            return {name for name in os.listdir(self.blob_dir) if len(name) == 12}
        except FileNotFoundError:
            return set()

    def _path(self, hash: str) -> str:
        return os.path.join(self.blob_dir, hash)