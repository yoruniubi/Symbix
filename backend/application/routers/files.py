from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException

from Symbix_sdk.tools.file_pipeline import (
    get_project_root,
)

router = APIRouter(prefix="/api/files", tags=["files"])
MAX_EDIT_BYTES = 5 * 1024 * 1024


def _resolve(path: str = ".") -> Path:
    raw_path = str(path or ".").strip()
    if not Path(raw_path).is_absolute():
        raw_path = str(Path(get_project_root()) / raw_path)
    try:
        return Path(raw_path).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"路径无效: {exc}") from exc


def _relative(path: Path) -> str:
    try:
        return path.relative_to(Path(get_project_root())).as_posix() or "."
    except ValueError:
        return str(path)


@router.get("/list")
async def list_directory(path: str = "."):
    directory = _resolve(path)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="目标不是文件夹")
    entries = []
    for item in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        # 与常见编辑器一致,隐藏的构建缓存不显示,但 .gitignore 等文件保留。
        if item.name in {".git", "node_modules", "__pycache__", ".venv", "venv"}:
            continue
        entries.append({
            "name": item.name,
            "path": _relative(item),
            "type": "directory" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })
    return {"path": _relative(directory), "entries": entries}


@router.get("/read")
async def read_workspace_file(path: str):
    file_path = _resolve(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if file_path.stat().st_size > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="文件过大,暂不支持在面板中编辑")
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="该文件不是 UTF-8 文本文件")
    return {"path": _relative(file_path), "name": file_path.name, "content": content}


@router.put("/write")
async def write_workspace_file(payload: dict):
    file_path = _resolve(payload.get("path", ""))
    content = payload.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content 必须是字符串")
    if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="文件过大")
    if file_path.exists() and file_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {"status": "ok", "path": _relative(file_path)}


@router.delete("/item")
async def delete_workspace_item(path: str):
    item = _resolve(path)
    if not item.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    if item == Path(get_project_root()):
        raise HTTPException(status_code=400, detail="不能删除项目根目录")
    if item.is_dir():
        shutil.rmtree(item)
    else:
        item.unlink()
    return {"status": "ok", "path": _relative(item)}