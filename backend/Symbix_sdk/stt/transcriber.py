from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional
from Symbix_sdk.resource_path import stt_bin_dir, stt_model_dir

class STTProviderError(Exception):
    """单个 provider 失败(引擎会捕获并尝试下一个)。"""

OnResult = Callable[[str], Awaitable[None]]


class STTProvider:
    """流式 provider 基类。"""

    name = "base"
    cloud = False  # 设置页区分 本地/云端 分组展示

    def available(self) -> bool:
        raise NotImplementedError

    async def start_stream(self, on_result: OnResult) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


# ---------------- SenseVoice.cpp(本地主) ----------------

class SenseVoiceProvider(STTProvider):
    """sense-voice-stream 子进程:stdout 每行一句,--use-vad 自动断句。

    二进制与模型随包分发:
      stt/bin/sense-voice-main.exe (+ dll)
      stt/model/sense-voice-small-q4_k.gguf
    """

    name = "sensevoice"

    def __init__(
        self,
        language: str = "auto",
        threads: int = 4,
        use_vad: bool = True,
    ) -> None:
        self.language = language
        self.threads = threads
        self.use_vad = use_vad
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None

    # ---- 路径解析:bin/model 目录里自动找 exe 和 gguf ----
    def _resolve_binary(self) -> Optional[str]:
        d = stt_bin_dir()
        if not d.exists():
            return None
        for cand in ("sense-voice-stream", "sense-voice-stream.exe",
                     "sense-voice-main.exe", "sense-voice-main"):
            p = d / cand
            if p.exists():
                return str(p)
        return None

    def _resolve_model(self) -> Optional[str]:
        d = stt_model_dir()
        if not d.exists():
            return None
        ggufs = sorted(d.glob("*.gguf"))
        return str(ggufs[0]) if ggufs else None

    def available(self) -> bool:
        return self._resolve_binary() is not None and self._resolve_model() is not None

    def _build_cmd(self) -> list[str]:
        cmd = [
            self._resolve_binary() or "",
            "-m", self._resolve_model() or "",
            "-l", self.language,
            "-t", str(self.threads),
        ]
        if self.use_vad:
            cmd.append("--use-vad")
        return cmd

    async def start_stream(self, on_result: OnResult) -> None:
        if self._process and self._process.returncode is None:
            return  # 已在跑
        if not self.available():
            raise STTProviderError(
                f"SenseVoice 不可用: bin={self._resolve_binary()} model={self._resolve_model()}"
            )

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._build_cmd(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as e:
            raise STTProviderError(f"SenseVoice 启动失败: {e}") from e

        async def _pump() -> None:
            assert self._process and self._process.stdout
            async for raw in self._process.stdout:
                text = raw.decode("utf-8", errors="replace").strip()
                if text:
                    try:
                        await on_result(text)
                    except Exception:
                        pass

        self._reader_task = asyncio.create_task(_pump())

    def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        self._process = None


# ---------------- 云端 Preset(占位,后续按官方文档补) ----------------

class FunASRCloudProvider(STTProvider):
    """阿里 FunASR 自建/云服务(WebSocket)。TODO: 等官方说明接入。"""

    name = "funasr"
    cloud = True

    def __init__(self, ws_url: str = "", token: str = "") -> None:
        self.ws_url = ws_url
        self.token = token

    def available(self) -> bool:
        return bool(self.ws_url)

    async def start_stream(self, on_result: OnResult) -> None:
        raise STTProviderError("FunASR 云端尚未接入(待提供官方说明)")


class OpenAIWhisperStreamProvider(STTProvider):
    """OpenAI /v1/audio/transcriptions 是文件式接口;流式需分段轮询。

    TODO: 后续接 WhisperStreaming 或等用户给 key 再定方案。
    """

    name = "openai"
    cloud = True

    def __init__(self, api_key: str = "", model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    async def start_stream(self, on_result: OnResult) -> None:
        raise STTProviderError("OpenAI Whisper 流式尚未接入")


class XfyunProvider(STTProvider):
    """科大讯飞语音听写 WebSocket API。TODO: 待 appId/apiKey 接入。"""

    name = "xfyun"
    cloud = True

    def __init__(self, app_id: str = "", api_key: str = "", api_secret: str = "") -> None:
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret

    def available(self) -> bool:
        return bool(self.app_id and self.api_key)

    async def start_stream(self, on_result: OnResult) -> None:
        raise STTProviderError("讯飞云端尚未接入(待 appId/apiKey)")


# ---------------- 注册表 + 引擎 ----------------

PROVIDER_CLASSES: dict[str, type[STTProvider]] = {
    SenseVoiceProvider.name: SenseVoiceProvider,
    FunASRCloudProvider.name: FunASRCloudProvider,
    OpenAIWhisperStreamProvider.name: OpenAIWhisperStreamProvider,
    XfyunProvider.name: XfyunProvider,
}


@dataclass
class STTConfig:
    """手动优先级 + 各引擎参数(persist 到 voice_config.json)。"""

    priority: list[str] = field(default_factory=lambda: ["sensevoice"])
    language: str = "auto"
    threads: int = 4
    use_vad: bool = True
    # 云端凭据(占位)
    funasr_ws_url: str = ""
    openai_api_key: str = ""
    xfyun_app_id: str = ""
    xfyun_api_key: str = ""
    xfyun_api_secret: str = ""

    def to_dict(self) -> dict:
        return {
            "priority": list(self.priority),
            "language": self.language,
            "threads": self.threads,
            "use_vad": self.use_vad,
            "funasr_ws_url": self.funasr_ws_url,
            "openai_api_key": self.openai_api_key,
            "xfyun_app_id": self.xfyun_app_id,
            "xfyun_api_key": self.xfyun_api_key,
            "xfyun_api_secret": self.xfyun_api_secret,
        }


class STTEngine:
    """管理当前活跃的流式会话;按优先级挑第一个可用的 provider。"""

    def __init__(self, config: STTConfig | None = None) -> None:
        self.config = config or STTConfig()
        self._active: Optional[STTProvider] = None

    def _build_provider(self, name: str) -> STTProvider:
        cfg = self.config
        if name == SenseVoiceProvider.name:
            return SenseVoiceProvider(language=cfg.language, threads=cfg.threads, use_vad=cfg.use_vad)
        if name == FunASRCloudProvider.name:
            return FunASRCloudProvider(ws_url=cfg.funasr_ws_url)
        if name == OpenAIWhisperStreamProvider.name:
            return OpenAIWhisperStreamProvider(api_key=cfg.openai_api_key)
        if name == XfyunProvider.name:
            return XfyunProvider(app_id=cfg.xfyun_app_id, api_key=cfg.xfyun_api_key, api_secret=cfg.xfyun_api_secret)
        raise STTProviderError(f"未知 STT 引擎: {name}")

    def status(self) -> dict:
        out = {}
        for name, cls in PROVIDER_CLASSES.items():
            inst = cls() if cls is SenseVoiceProvider else self._build_provider(name)
            out[name] = {"available": inst.available(), "cloud": cls.cloud}
        return out

    @property
    def running(self) -> bool:
        return self._active is not None

    async def start(self, on_result: OnResult) -> str:
        """按优先级启动第一个可用的引擎,返回实际命中的名字。"""
        await self.stop()
        errors: list[str] = []
        for name in self.config.priority:
            try:
                p = self._build_provider(name)
                if not p.available():
                    errors.append(f"{name}: 不可用")
                    continue
                await p.start_stream(on_result)
                self._active = p
                return name
            except STTProviderError as e:
                errors.append(f"{name}: {e}")
        raise STTProviderError("所有 STT 引擎均不可用 → " + "; ".join(errors))

    async def stop(self) -> None:
        if self._active:
            self._active.stop()
            self._active = None


# 全局单例(state.py 引用)
stt_engine = STTEngine()
