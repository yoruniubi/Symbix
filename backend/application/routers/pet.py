
from __future__ import annotations
import asyncio
import json as _json
import os
import shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from application.services.memory_ops import format_sse
from application.services.pet_action import LOOP_ACTIONS, SSE_SHUTDOWN, normalize_pet_action, pet_action


# 前端静态资源目录(相对于 backend 运行目录)
# codex_pet:Codex 桌宠导入(pet.json + spritesheet 位图动画)
# pixiv_pet:pet-forge 生成(base.svg + states.json,烘焙出 spritesheet 后可切换)
_PUBLIC_DIR = Path(os.environ.get("PET_PUBLIC_DIR", "../Symbix_frontend/public")).resolve()
_CODEX_PET_DIR = Path(os.environ.get("PET_CODEX_DIR", str(_PUBLIC_DIR / "codex_pet"))).resolve()
_PIXIV_PET_DIR = Path(os.environ.get("PET_PIXIV_DIR", str(_PUBLIC_DIR / "pixiv_pet"))).resolve()
# pet-forge skill 脚本目录(校验/烘焙/打包);按后端仓库结构推导,不写死盘符
_FORGE_SCRIPTS = Path(
    os.environ.get(
        "PET_FORGE_SCRIPTS",
        str(Path(__file__).resolve().parents[2] / "Symbix_sdk" / "skill" / "installed_skills" / "pet-forge" / "scripts"),
    )
).resolve()

router = APIRouter(tags=["pet"])


class PetActionRequest(BaseModel):
    action: str = Field(..., description="动作名，如 waving / jumping / happy")
    bubble: str = Field("", description="可选气泡文案")
    source: str = Field("api", description="来源标记")


class PetBakeRequest(BaseModel):
    name: str = Field(..., description="pixiv_pet 下的主题目录名")


@router.get("/pet/status")
async def pet_status():
    """当前桌宠状态快照。"""
    return {
        "status": "ok",
        "last_action": pet_action.last_action,
        "recent": pet_action.recent(5),
        "loop_actions": sorted(LOOP_ACTIONS),
    }


@router.post("/pet/action")
async def trigger_pet_action(req: PetActionRequest):
    """手动触发桌宠动作（调试或非 tool 调用）。"""
    action = (req.action or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="action 不能为空")
    event = pet_action.emit(
        action,
        bubble=req.bubble or "",
        source=req.source or "api",
    )
    return {
        "status": "ok",
        "event": event,
        "normalized": event.get("action"),
    }


@router.get("/pet/events")
async def pet_events(
    request: Request,
    replay: int = Query(0, ge=0, le=8, description="连接时回放最近 N 条事件"),
):
    """Home 窗口订阅桌宠动作的 SSE 流。

    事件格式与聊天 SSE 一致：
      event: pet_action
      data: {"type":"pet_action","action":"waving",...}

    另有 heartbeat（约 20s）保持连接。
    """

    async def event_gen():
        queue = pet_action.subscribe()
        try:
            # 连接问候
            yield format_sse(
                {
                    "type": "pet_hello",
                    "last_action": pet_action.last_action,
                    "message": "pet events connected",
                }
            )
            # 可选回放
            if replay > 0:
                for ev in pet_action.recent(replay):
                    yield format_sse(ev)

            while True:
                # "Waiting for connections to close"
                if pet_action.closed:
                    break
                try:
                    if await request.is_disconnected():
                        break
                except Exception:
                    break

                try:
                    # 心跳间隔 3s，必须小于 uvicorn timeout_keep_alive（5s），避免竞态断开
                    event = await asyncio.wait_for(queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    if pet_action.closed:
                        break
                    try:
                        if await request.is_disconnected():
                            break
                    except Exception:
                        break
                    yield format_sse(
                        {
                            "type": "pet_heartbeat",
                            "last_action": pet_action.last_action,
                            "ts": __import__("time").time(),
                        }
                    )
                    continue
                except asyncio.CancelledError:
                    break

                if event is SSE_SHUTDOWN or pet_action.closed:
                    break
                yield format_sse(event)
        except asyncio.CancelledError:
            pass
        finally:
            pet_action.unsubscribe(queue)


    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class PetImportPathRequest(BaseModel):
    source_path: str = Field(..., description="本机桌宠文件夹绝对路径")
    folder_name: str | None = Field(None, description="目标文件夹名，默认取源目录名")


def _validate_pet_folder(source: Path) -> dict:
    """校验源目录是否为合法 Codex 桌宠文件夹，返回 pet.json 内容。"""
    if not source.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录: {source}")

    pet_json = source / "pet.json"
    if not pet_json.is_file():
        raise HTTPException(status_code=400, detail="文件夹内未找到 pet.json")

    try:
        meta = _json.loads(pet_json.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pet.json 解析失败: {e}") from e

    return meta if isinstance(meta, dict) else {}


def _safe_folder_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise HTTPException(status_code=400, detail="文件夹名不合法")
    return cleaned


@router.post("/pet/import-path")
async def pet_import_from_path(req: PetImportPathRequest):
    """从本机路径直接拷贝桌宠文件夹到 public/codex_pet/{folder_name}/。

    桌面端（Tauri）选完目录后只传路径，走本地 shutil 拷贝，
    避免浏览器 multipart 上传大文件夹卡住 / 弹出「是否上传」确认框。
    """
    source = Path(req.source_path).expanduser().resolve()
    meta = _validate_pet_folder(source)

    folder_name = _safe_folder_name(req.folder_name or source.name)
    target_dir = _CODEX_PET_DIR / folder_name

    try:
        _CODEX_PET_DIR.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        # 本地磁盘拷贝，几 MB 通常 < 1s
        shutil.copytree(source, target_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拷贝失败: {e}") from e

    files_saved = sum(1 for p in target_dir.rglob("*") if p.is_file())
    preview = "spritesheet.webp"
    if not (target_dir / preview).is_file():
        for cand in ("spritesheet.png", "preview.webp", "preview.png"):
            if (target_dir / cand).is_file():
                preview = cand
                break

    display_name = (
        meta.get("displayName")
        or meta.get("display_name")
        or meta.get("name")
        or folder_name
    )

    return {
        "status": "ok",
        "folder": str(target_dir),
        "folder_name": folder_name,
        "display_name": display_name,
        "preview": f"/codex_pet/{folder_name}/{preview}",
        "files_saved": files_saved,
        "message": f"皮肤文件夹 '{folder_name}' 导入成功",
    }



@router.post("/pet/import")
async def pet_import_folder(
    files: List[UploadFile] = File(..., description="文件夹内关键文件"),
    folder_name: str = Form(..., description="目标文件夹名"),
):
    """浏览器回退：仅上传关键文件（pet.json / spritesheet 等），避免整夹上传卡死。"""
    folder_name = _safe_folder_name(folder_name)

    target_dir = _CODEX_PET_DIR / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    target_dir.mkdir(parents=True, exist_ok=True)

    # 只接受白名单文件，防止把中间帧整包拖进来卡死
    allow_names = {
        "pet.json",
        "spritesheet.webp",
        "spritesheet.png",
        "spritesheet.json",
        "preview.webp",
        "preview.png",
    }
    allow_ext = {".webp", ".png", ".jpg", ".jpeg", ".json"}

    saved_count = 0
    for f in files:
        rel_name = (f.filename or f"unknown_{saved_count}").replace("\\", "/")
        parts = rel_name.split("/")
        if parts and parts[0] == folder_name:
            parts = parts[1:]
        # 只保留根目录文件，忽略深层 frames/
        if len(parts) != 1:
            continue
        base = parts[0]
        if base not in allow_names and Path(base).suffix.lower() not in allow_ext:
            continue
        if base not in allow_names and not base.startswith("spritesheet"):
            # 额外限制：非白名单的图片不收，避免几百帧拖垮
            if Path(base).suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"}:
                continue

        dest_path = target_dir / base
        content = await f.read()
        dest_path.write_bytes(content)
        saved_count += 1

    pet_json_path = target_dir / "pet.json"
    if not pet_json_path.is_file():
        shutil.rmtree(target_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="上传内容缺少 pet.json")

    display_name = folder_name
    try:
        meta = _json.loads(pet_json_path.read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            display_name = (
                meta.get("displayName")
                or meta.get("display_name")
                or meta.get("name")
                or folder_name
            )
    except Exception:
        pass

    preview = "spritesheet.webp"
    if not (target_dir / preview).is_file():
        for cand in ("spritesheet.png", "preview.webp", "preview.png"):
            if (target_dir / cand).is_file():
                preview = cand
                break

    return {
        "status": "ok",
        "folder": str(target_dir),
        "folder_name": folder_name,
        "display_name": display_name,
        "preview": f"/codex_pet/{folder_name}/{preview}",
        "files_saved": saved_count,
        "message": f"皮肤文件夹 '{folder_name}' 导入成功",
    }


# ---------------------------------------------------------------------------
# 皮肤列表 / pet-forge 主题烘焙
# ---------------------------------------------------------------------------

# 内置皮肤(随仓库分发),其余磁盘上的都算已导入
_BUILTIN_SKINS = frozenset({"frieren"})
_SPRITESHEET_CANDIDATES = ("spritesheet.webp", "spritesheet.png", "preview.webp", "preview.png")


def _first_existing(folder: Path, names: tuple[str, ...]) -> str | None:
    for name in names:
        if (folder / name).is_file():
            return name
    return None


def _read_json_quiet(path: Path) -> dict:
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@router.get("/pet/skins")
async def pet_list_skins():
    """扫描静态资源目录,返回当前磁盘上真正存在的皮肤。

    以前皮肤列表只存在前端 localStorage(仅记「导入过什么」),
    pet-forge 直接把产物写进 public/pixiv_pet/,前端根本不知道它存在。
    ready=False 表示只有 rig 源文件、还没烘焙出 spritesheet(不能切换,只能预览)。
    """
    skins: list[dict] = []

    if _CODEX_PET_DIR.is_dir():
        for folder in sorted(_CODEX_PET_DIR.iterdir()):
            if not folder.is_dir():
                continue
            meta = _read_json_quiet(folder / "pet.json")
            if not meta:
                continue
            sheet = _first_existing(folder, _SPRITESHEET_CANDIDATES)
            skins.append(
                {
                    "id": f"codex_{folder.name}",
                    "folder": folder.name,
                    "displayName": meta.get("displayName") or meta.get("name") or folder.name,
                    "description": meta.get("description") or "",
                    "preview": f"/codex_pet/{folder.name}/{sheet or 'spritesheet.webp'}",
                    "origin": "codex",
                    "builtin": folder.name in _BUILTIN_SKINS,
                    "ready": sheet is not None,
                }
            )

    if _PIXIV_PET_DIR.is_dir():
        for folder in sorted(_PIXIV_PET_DIR.iterdir()):
            if not folder.is_dir():
                continue
            meta = _read_json_quiet(folder / "theme.json")
            if not meta and not (folder / "base.svg").is_file():
                continue
            sheet = _first_existing(folder, _SPRITESHEET_CANDIDATES)
            skins.append(
                {
                    "id": f"pixiv_{folder.name}",
                    "folder": folder.name,
                    "displayName": meta.get("name") or folder.name,
                    "description": meta.get("description") or "",
                    # 未烘焙时退回 base.svg(静态矢量图,至少能看到长什么样)
                    "preview": f"/pixiv_pet/{folder.name}/{sheet or 'base.svg'}",
                    "origin": "pixiv",
                    "builtin": folder.name in _BUILTIN_SKINS,
                    "ready": sheet is not None,
                    "capabilities": meta.get("capabilities") or [],
                }
            )

    return {"skins": skins}


def _load_forge_script(module_name: str):
    """按文件路径加载 pet-forge 脚本(它们不在 backend 的 import 路径里)。"""
    import importlib.util
    import sys

    path = _FORGE_SCRIPTS / f"{module_name}.py"
    if not path.is_file():
        raise HTTPException(status_code=500, detail=f"pet-forge 脚本缺失: {path}")
    spec = importlib.util.spec_from_file_location(f"pet_forge_{module_name}", path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail=f"pet-forge 脚本无法加载: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@router.post("/pet/bake")
async def pet_bake_theme(req: PetBakeRequest):
    """把 pixiv_pet 下的 rig 源文件烘焙成可播放的 spritesheet(+ pet.json)。

    rig(base.svg + states.json)本身不能播放,必须经过 bake → 拼图 才能被
    Home.vue 的 Pixi 管线加载;旧版本生成流程漏了这步,皮肤就一直「存在但不可见」。
    """
    name = _safe_folder_name(req.name)
    theme_dir = _PIXIV_PET_DIR / name
    if not theme_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"主题目录不存在: {name}")
    rig = theme_dir / "base.svg"
    states = theme_dir / "states.json"
    if not rig.is_file() or not states.is_file():
        raise HTTPException(status_code=400, detail="主题目录缺少 base.svg / states.json")

    def _run() -> dict:
        mod = _load_forge_script("build_theme")
        return mod.build_theme(
            name=name,
            rig_path=rig,
            states_path=states,
            out_dir=theme_dir,
        )

    try:
        result = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"烘焙失败: {e}") from e

    return {"status": "ok", **result}

