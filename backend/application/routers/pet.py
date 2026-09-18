
from __future__ import annotations
import asyncio
import json as _json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from application.services.memory_ops import format_sse
from application.services.pet_action import LOOP_ACTIONS, SSE_SHUTDOWN, normalize_pet_action, pet_action
from Symbix_sdk.color_extract import extract_palette_b64, palette_to_hint


# 前端静态资源目录(相对于 backend 运行目录)
# codex_pet:Codex 桌宠导入(pet.json + spritesheet 位图动画)
# pixiv_pet:pet-forge 生成的 SVG 桌宠(base.svg + states.json + theme.json)
_PUBLIC_DIR = Path(os.environ.get("PET_PUBLIC_DIR", "../Symbix_frontend/public")).resolve()
_CODEX_PET_DIR = Path(os.environ.get("PET_CODEX_DIR", str(_PUBLIC_DIR / "codex_pet"))).resolve()
_PIXIV_PET_DIR = Path(os.environ.get("PET_PIXIV_DIR", str(_PUBLIC_DIR / "pixiv_pet"))).resolve()

# pet-forge 脚本目录
# pet.py 在 backend/application/routers/,脚本在 backend/Symbix_sdk/skill/installed_skills/pet-forge/scripts/
_PET_FORGE_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "Symbix_sdk" / "skill" / "installed_skills" / "pet-forge" / "scripts"
if str(_PET_FORGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PET_FORGE_SCRIPTS))

import importlib.util
def _load_script(script_name: str):
    """用 importlib.util 加载指定脚本模块，返回 module 对象。"""
    script_path = _PET_FORGE_SCRIPTS / f"{script_name}.py"
    if not script_path.exists():
        raise ImportError(f"{script_name}.py not found at {script_path}")
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

try:
    # 先加载 _common 和 validate_rig，因为其他脚本依赖它们
    _common = _load_script('_common')
    validate_rig_mod = _load_script('validate_rig')
    generate_rig_mod = _load_script('generate_rig')
    generate_states_batch_mod = _load_script('generate_states_batch')
    pack_theme_mod = _load_script('pack_theme')

    # 提取需要的函数和异常类
    generate_rig = generate_rig_mod.generate_rig
    RigGenerationError = generate_rig_mod.RigGenerationError
    generate_states_all = generate_states_batch_mod.generate_states_all
    StatesGenerationError = generate_states_batch_mod.StatesGenerationError
    pack_theme = pack_theme_mod.pack_theme
    # 从 _common 提取辅助函数
    list_part_ids_from_svg = _common.list_part_ids_from_svg
except ImportError as e:
    print(f"[pet] 无法导入 pet-forge 脚本: {e}")
    generate_rig = None
    generate_states_all = None
    pack_theme = None
    RigGenerationError = Exception  # 占位
    StatesGenerationError = Exception
except Exception as e:
    print(f"[pet] 加载 pet-forge 脚本时出现异常: {e}")
    generate_rig = None
    generate_states_all = None
    pack_theme = None
    RigGenerationError = Exception
    StatesGenerationError = Exception

router = APIRouter(tags=["pet"])

class PetGenerateRequest(BaseModel):
    name: str = Field(..., description="皮肤名称(将用作文件夹名)")
    prompt: str = Field(..., description="外观描述,用于生成 rig 和动画")
    ref_image: Optional[str] = Field(None, description="参考图 base64 dataURL;无视觉模型时自动提取主色注入提示词")


class PetActionRequest(BaseModel):
    action: str = Field(..., description="动作名，如 waving / jumping / happy")
    bubble: str = Field("", description="可选气泡文案")
    source: str = Field("api", description="来源标记")


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



@router.post("/pet/generate")
async def pet_generate(req: PetGenerateRequest):
    """调用 pet-forge 完整流水线生成新桌宠皮肤（SVG rig + 动画状态）。
    
    流程：
    1. generate_rig → base.svg
    2. generate_states_batch → states.json（分批生成）
    3. derive_mirrors（自动镜像补全 left 部件）
    4. validate_states 校验
    5. pack_theme → 主题目录（含 base.svg, states.json, theme.json）
    6. 复制到 public/pixiv_pet/{name}/ 供前端访问
    """
    if generate_rig is None or generate_states_all is None or pack_theme is None:
        raise HTTPException(status_code=503, detail="pet-forge 脚本未正确加载")

    # 安全校验文件夹名
    folder_name = req.name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="皮肤名称不能为空")
    if "/" in folder_name or "\\" in folder_name or ".." in folder_name:
        raise HTTPException(status_code=400, detail="皮肤名称包含非法字符")

    # 目标目录:public/pixiv_pet/{folder_name}
    target_dir = _PIXIV_PET_DIR / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    # 临时工作目录(在系统临时目录下)
    import tempfile
    work_dir = Path(tempfile.mkdtemp(prefix="pet_forge_"))
    try:
        # 1. 生成 rig
        def progress(msg: str):
            print(f"[pet-forge] {msg}")

        # 无视觉模型也可用:若带参考图,提取主色拼进 prompt,让 SVG 颜色尽量贴合
        effective_prompt = req.prompt
        color_tag = ""
        if req.ref_image:
            try:
                hexes = extract_palette_b64(req.ref_image)
                color_tag = palette_to_hint(hexes)
            except Exception as e:
                print(f"[pet-forge] 参考图取色失败(忽略): {e}")
        if color_tag:
            effective_prompt = f"{req.prompt}\n\n{color_tag}"

        svg_text = generate_rig(
            description=effective_prompt,
            name=folder_name,
            max_retries=3,
            progress=progress,
        )

        # 2. 从 SVG 提取 part ids（用于 states 生成）
        part_ids = list_part_ids_from_svg(svg_text)
        if not part_ids:
            raise HTTPException(status_code=400, detail="生成的 SVG 中未找到任何部件")

        # 3. 生成 states（全量，含镜像补全）
        states = generate_states_all(
            part_ids=part_ids,
            name=folder_name,
            description=effective_prompt,
            max_retries=3,
            progress=progress,
            apply_mirrors=True,
        )

        # 4. 打包主题(会做最终校验);有参考图取色则用其作为 palette 落盘
        palette_dict = None
        if color_tag and req.ref_image:
            try:
                hexes = extract_palette_b64(req.ref_image)
                from Symbix_sdk.color_extract import colors_to_pet_slots

                palette_dict = colors_to_pet_slots(hexes) or None
            except Exception as e:
                print(f"[pet-forge] palette 落盘失败(忽略,用默认色): {e}")
        theme = pack_theme(
            name=folder_name,
            svg_text=svg_text,
            states=states,
            out_dir=work_dir,
            version="1.0.0",
            description=req.prompt,
            palette=palette_dict,
            # schema_path 可选,不传
        )

        # 5. 将工作目录内容复制到 public/pixiv_pet/{folder_name}
        shutil.copytree(work_dir, target_dir, dirs_exist_ok=True)

        # 6. 构建返回信息
        preview = f"/pixiv_pet/{folder_name}/base.svg"  # 用 SVG 作为预览
        return {
            "status": "ok",
            "folder": str(target_dir),
            "folder_name": folder_name,
            "display_name": folder_name,
            "preview": preview,
            "files_saved": sum(1 for _ in target_dir.rglob("*") if _.is_file()),
            "message": f"皮肤 '{folder_name}' 生成成功",
            "capabilities": theme.get("capabilities", []),
        }

    except RigGenerationError as e:
        raise HTTPException(status_code=500, detail=f"Rig 生成失败: {e}")
    except StatesGenerationError as e:
        raise HTTPException(status_code=500, detail=f"States 生成失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")
    finally:
        # 清理临时目录
        shutil.rmtree(work_dir, ignore_errors=True)


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
