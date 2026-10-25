from pathlib import Path
import shutil
from fastapi import APIRouter, HTTPException
import Symbix_sdk
from Symbix_sdk.tools.file_pipeline import (
    get_project_root,
    add_workspace_root,
    remove_workspace_root,
    clear_workspace_roots,
    workspace_roots,
    forbidden_roots,
)

router = APIRouter(prefix="/api/files", tags=["files"])
MAX_EDIT_BYTES = 5 * 1024 * 1024
SKILL_ROOTS_DIR = Path(Symbix_sdk.__file__).resolve().parent / "skill" / "installed_skills"


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


def _forbidden_hint() -> str:
    return " / ".join(str(p) for p in forbidden_roots()[:3]) + " 等系统保护目录不可作为工作区"


def _read_candidates(path: str) -> list[Path]:
    """读文件的候选路径:常规解析优先,再兜回 skill 目录。

    pet-forge 这类 skill 的脚本以 skill 目录为工作目录运行,Agent 传进工具的参数
    常是 `assets/fixtures/xx/base.svg` 这种相对路径 —— 按项目根解析必然 404,
    而文件其实躺在 installed_skills/<skill>/ 下。补一层候选根,预览就能读到。
    """
    candidates = [_resolve(path)]
    raw = str(path or "").strip()
    if raw and not Path(raw).is_absolute():
        try:
            for skill_dir in sorted(SKILL_ROOTS_DIR.iterdir()):
                if skill_dir.is_dir():
                    candidates.append((skill_dir / raw).resolve())
        except OSError:
            pass
    return candidates


@router.get("/workspace")
async def get_workspace():
    """返回当前会话内 Agent 被授权的外部目录列表(FilePanel 浏览过的)。"""
    return {"roots": workspace_roots()}


@router.post("/workspace")
async def add_workspace(payload: dict):
    """把某个外部目录加入 Agent 可读区(FilePanel 浏览即授权)。

    body: { "path": "/abs/dir" }  —— 传 null/"" 则清空全部授权。
    命中系统保护目录会被拒绝。
    """
    raw = (payload or {}).get("path")
    if raw is None or not str(raw).strip():
        clear_workspace_roots()
        return {"status": "ok", "roots": workspace_roots()}
    try:
        p = add_workspace_root(str(raw))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 二次确认不在禁止区(目录本身合法但名字撞禁止列表的情况)
    for fr in forbidden_roots():
        try:
            if Path(p) == Path(fr) or Path(fr) in Path(p).parents:
                remove_workspace_root(str(raw))
                raise HTTPException(status_code=403, detail=_forbidden_hint())
        except Exception:
            continue
    return {"status": "ok", "roots": workspace_roots()}


@router.get("/list")
async def list_directory(path: str = "."):
    directory = _resolve(path)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="目标不是文件夹")
    # 浏览即授权:项目外的目录(用户通过文件面板主动打开)自动进入 Agent 可读区
    raw_path = str(path or ".").strip()
    if raw_path and (Path(raw_path).is_absolute()):
        try:
            add_workspace_root(str(directory))
        except (ValueError, OSError):
            pass  # 授权失败不影响浏览
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


@router.get("/raw")
async def read_raw_file(path: str):
    """按原始字节读文件(图片预览用),带 Content-Type 返回。

    ChatMessage 把工具输出里的 `[Image saved: <路径>]`(MCP 返回的图片内容
    由 connector 落盘)渲染成真图,走这个端点拿字节。只允许图片后缀,
    且命中系统保护目录直接拒绝。
    """
    from fastapi import Response
    file_path = _resolve(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    for forbidden in forbidden_roots():
        prefix = str(forbidden).rstrip("\\/")
        if str(file_path).lower().startswith(prefix.lower()):
            raise HTTPException(status_code=403, detail="系统保护目录不可读")
    if file_path.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大")
    ext = file_path.suffix.lower()
    media = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
    }
    if ext not in media:
        raise HTTPException(status_code=415, detail="仅支持图片文件")
    return Response(
        content=file_path.read_bytes(),
        media_type=media[ext],
        headers={"Cache-Control": "max-age=3600"},
    )


@router.get("/read")
async def read_workspace_file(path: str):
    candidates = _read_candidates(path)
    file_path = next((c for c in candidates if c.is_file()), candidates[0])
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