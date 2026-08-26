from __future__ import annotations

import asyncio
import json
import os.path as osp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from Symbix_sdk.config.voice_config import VoiceConfigManager
from Symbix_sdk.tts.synthesizer import tts_engine, TTSProviderError
from Symbix_sdk.stt.transcriber import stt_engine, STTProviderError

router = APIRouter(tags=["voice"])

_CONFIG_PATH = osp.join(
    osp.dirname(osp.abspath(__file__)),
    "..", "..", "Symbix_sdk", "config", "voice_config.json",
)
voice_cfg = VoiceConfigManager(_CONFIG_PATH)

# 把配置热更新到引擎单例
tts_engine.config = voice_cfg.tts
stt_engine.config = voice_cfg.stt


# ---------------- 配置 ----------------

@router.get("/voice/config")
async def get_voice_config():
    return {
        "tts": voice_cfg.tts.to_dict(),
        "stt": voice_cfg.stt.to_dict(),
        "status": {
            "tts": tts_engine.status(),
            "stt": stt_engine.status(),
        },
    }


class VoiceConfigPatch(BaseModel):
    tts: dict | None = None
    stt: dict | None = None


@router.post("/voice/config")
async def update_voice_config(patch: VoiceConfigPatch):
    if patch.tts:
        voice_cfg.apply_tts_patch(patch.tts)
        tts_engine.config = voice_cfg.tts
    if patch.stt:
        # STT 改动时若正在录音,先停掉旧引擎,下次 start 用新参数
        await stt_engine.stop()
        voice_cfg.apply_stt_patch(patch.stt)
        stt_engine.config = voice_cfg.stt
    return {"status": "ok"}


# ---------------- TTS ----------------

class TTSRequest(BaseModel):
    text: str
    speed: float | None = None  # 覆盖默认语速(0.5~2.0)


@router.post("/voice/tts")
async def synthesize(req: TTSRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    engine_backup = tts_engine.config.speed
    if req.speed is not None:
        tts_engine.config.speed = max(0.5, min(2.0, req.speed))
    try:
        result = await tts_engine.synthesize(text[:2000])
    except TTSProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    finally:
        tts_engine.config.speed = engine_backup

    return StreamingResponse(
        iter([result.audio]),
        media_type=result.mime,
        headers={"X-Voice-Engine": result.engine},
    )


# ---------------- STT(实时流式,SSE 推送) ----------------

_subscribers: set[asyncio.Queue] = set()


def _broadcast(text: str) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(text)
        except Exception:
            pass


async def _on_result(text: str) -> None:
    """SenseVoice pump 在事件循环内读子进程 stdout,直接广播即可。"""
    _broadcast(text)


@router.post("/voice/stt/start")
async def stt_start():
    """拉起流式识别(按手动优先级选引擎)。"""
    try:
        name = await stt_engine.start(_on_result)
        return {"status": "ok", "engine": name}
    except STTProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/voice/stt/stop")
async def stt_stop():
    await stt_engine.stop()
    return {"status": "ok"}


@router.get("/voice/stt/events")
async def stt_events(request: Request):
    """SSE:识别结果文本逐句推送。前端 EventSource 订阅。"""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    text = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
