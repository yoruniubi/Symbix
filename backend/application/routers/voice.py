from __future__ import annotations
import asyncio
import json
import os.path as osp
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from Symbix_sdk.config.voice_config import VoiceConfigManager
from Symbix_sdk.tts.synthesizer import tts_engine, TTSProviderError
from Symbix_sdk.tts import edge_update
from Symbix_sdk.stt.transcriber import (
    stt_engine,
    STTProviderError,
    OpenAIWhisperStreamProvider,
)

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
            "tts": await tts_engine.status(),
            "stt": stt_engine.status(),
            # edge-tts 版本:设置页展示,也方便一眼看出是不是被微软的令牌换代打中了
            "edgeVersion": edge_update.installed_version(),
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
        tts_engine.reload()  # 清 provider 缓存,让新 api_key/base_url 生效
    if patch.stt:
        # STT 改动时若正在录音,先停掉旧引擎,下次 start 用新参数
        await stt_engine.stop()
        voice_cfg.apply_stt_patch(patch.stt)
        stt_engine.config = voice_cfg.stt
    return {"status": "ok"}


class EdgeAutoUpdatePatch(BaseModel):
    enabled: bool


@router.post("/voice/config/edge-auto-update")
async def set_edge_auto_update(patch: EdgeAutoUpdatePatch):
    """设置页的「自动更新 edge-tts」开关。

    单独给一个接口而不是走 POST /voice/config:开关改一下就要立刻生效,没必要把
    表单里其它未保存的字段一并提交。`tts_engine.config` 与 `voice_cfg.tts` 是同一个
    对象(见文件顶部),所以 apply_tts_patch 会直接热更新到引擎。
    """
    voice_cfg.apply_tts_patch({"edge_auto_update": bool(patch.enabled)})
    return {"status": "ok", "edge_auto_update": voice_cfg.tts.edge_auto_update}


# ---------------- TTS ----------------

class TTSRequest(BaseModel):
    text: str
    speed: float | None = None  # 覆盖默认语速(0.5~2.0)
    engine: str | None = None   # 指定试听引擎(如 "edge"/"openai"),不传则按优先级链


@router.post("/voice/tts")
async def synthesize(req: TTSRequest):
    if not voice_cfg.tts.enabled:
        raise HTTPException(status_code=403, detail="TTS 功能已关闭")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    engine_backup = tts_engine.config.speed
    if req.speed is not None:
        tts_engine.config.speed = max(0.5, min(2.0, req.speed))
    try:
        result = await tts_engine.synthesize(text[:2000], engine=req.engine)
    except TTSProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    finally:
        tts_engine.config.speed = engine_backup

    return StreamingResponse(
        iter([result.audio]),
        media_type=result.mime,
        headers={"X-Voice-Engine": result.engine},
    )


# ---------------- edge-tts 手动升级 ----------------
#
# 微软会周期性轮换 Sec-MS-GEC 令牌代次,旧版 edge-tts 一律 403。引擎侧已有
# 「遇 403 自动升库并重试」的自愈(见 synthesizer.TTSEngine._edge_selfheal),
# 这个接口是给用户的兜底:一键升级,升级后会清模块缓存,下次合成直接用新版。
# 当前版本号随风 /voice/config 的 status.edgeVersion 返回。

@router.post("/voice/tts/edge/upgrade")
async def edge_tts_upgrade():
    """立即升级 edge-tts。返回 {ok, detail, installed}。"""
    ok, detail = await asyncio.to_thread(edge_update.ensure_updated)
    return {"ok": ok, "detail": detail, "installed": edge_update.installed_version()}


# ---------------- STT(实时流式,SSE 推送) ----------------

_subscribers: set[asyncio.Queue] = set()


def _clean_sensevoice(text: str) -> str:
    """洗掉 sense-voice --use-prefix 带出的元数据标记。

    形如 "<|zh|><|NEUTRAL|><|Speech|>你好世界",只保留正文。
    逐个去掉 <|...|> / em <|zh|> ... </|zh|> 包裹,并规整空格。
    """
    import re

    t = text
    # 剥掉成对的 em 包裹 <|zh|>xxx</|zh|> (保留内部正文)
    t = re.sub(r"<\|[^>]+?\|>(.*?)</\|[^>]+?\|>", r"\1", t, flags=re.S)
    # 剥掉残留的 <|xxx|>
    t = re.sub(r"<\|[^>]*?\|>", "", t)
    return t.strip()


def _broadcast(text: str) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(text)
        except Exception:
            pass


async def _on_result(text: str) -> None:
    """SenseVoice pump 在事件循环内读子进程 stdout,直接广播即可。"""
    cleaned = _clean_sensevoice(text)
    if cleaned:
        _broadcast(cleaned)


@router.post("/voice/stt/start")
async def stt_start():
    if not voice_cfg.stt.enabled:
        raise HTTPException(status_code=403, detail="STT 功能已关闭")
    """拉起流式识别(仅本地流式引擎能用;云端文件式走 upload)。"""
    try:
        name = await stt_engine.start(_on_result)
        return {"status": "ok", "engine": name}
    except STTProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/voice/stt/devices")
async def stt_devices():
    """枚举本机音频捕获设备,供设置页把“麦克风 ID”变成下拉选择。"""
    prov = stt_engine._build_provider("sensevoice")
    try:
        devs = await prov.list_devices()
    except STTProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"devices": devs}


@router.post("/voice/stt/upload")
async def stt_upload(file: UploadFile = File(...)):
    if not voice_cfg.stt.enabled:
        raise HTTPException(status_code=403, detail="STT 功能已关闭")
    """前端录音 → 上传音频 → 交给 OpenAI 兼容转录接口(自建网关/官方)。

    命中 openai 引擎则转发;否则 400 提示。返回 {text}。
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空音频")
    name = file.filename or "audio.wav"
    # 找优先级里第一个 openai 引擎(云端文件式)
    provider = None
    for eng in stt_engine.config.priority:
        if eng == OpenAIWhisperStreamProvider.name:
            provider = stt_engine._build_provider(eng)
            break
    if provider is None or not provider.available():
        raise HTTPException(
            status_code=400,
            detail="STT 未配置 OpenAI 兼容引擎(请在设置里填 base_url/api_key,并把 openai 加入优先级)",
        )
    try:
        text = await provider.transcribe_file(raw, name)
    except STTProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    # 同时广播给 SSE 订阅者(聊天输入框能直接看到)
    if text:
        _broadcast(text)
    return {"text": text}


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
