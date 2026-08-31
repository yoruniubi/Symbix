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

    流式 VAD 是【信号处理实现】(非模型),参数 chunk_size / min-mute 
    / max-nomute-chunks 共同控制断句。二进制 + 模型随包分发:
      stt/bin/sense-voice-stream(.exe) (+ dll)
      stt/model/sense-voice-small-q4_k.gguf

    该 exe 未就位时 available() 返回 False,引擎优雅跳过,不阻断启动。
    """

    name = "sensevoice"

    def __init__(
        self,
        language: str = "auto",
        threads: int = 4,
        use_vad: bool = True,
        chunk_size: int = 100,          # 流式 VAD chunk 大小(ms)
        min_mute_chunks: int = 10,      # 静音最少块数 → 判定一句结束
        max_nomute_chunks: int = 80,    # 最大非静音块数 → 强制切句
        use_prefix: bool = False,       # sensevoice 额外信息(语种/情感/事件/itn)
        use_itn: bool = True,           # 逆文本正则化(补标点)
        capture_device: int = -1,       # -1 = 默认麦克风
        no_gpu: bool = False,           # -ng 强制 CPU(默认按 CLI false)
        flash_attn: bool = False,       # -fa flash attention 解码
    ) -> None:
        self.language = language
        self.threads = threads
        self.use_vad = use_vad
        self.chunk_size = chunk_size
        self.min_mute_chunks = min_mute_chunks
        self.max_nomute_chunks = max_nomute_chunks
        self.use_prefix = use_prefix
        self.use_itn = use_itn
        self.capture_device = capture_device
        self.no_gpu = no_gpu
        self.flash_attn = flash_attn
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
        bin_ = self._resolve_binary()
        model = self._resolve_model()
        assert bin_ and model
        cmd = [
            bin_,
            "-m", model,
            "-l", self.language,
            "-t", str(self.threads),
        ]
        if self.available() and self.use_vad:
            cmd += [
                "--use-vad",
                "--chunk_size", str(self.chunk_size),
                "-mmc", str(self.min_mute_chunks),
                "-mnc", str(self.max_nomute_chunks),
            ]
        if self.use_prefix:
            cmd.append("--use-prefix")
        if self.use_itn:
            cmd.append("--use-itn")
        if self.no_gpu:
            cmd.append("-ng")
        if self.flash_attn:
            cmd.append("-fa")
        if self.capture_device >= 0:
            cmd += ["-c", str(self.capture_device)]
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
    """OpenAI 兼容 /v1/audio/transcriptions 文件式接口(云端/自建网关)。

    配合前端:浏览器录音(MediaRecorder)→ 上传 wav → 后端 httpx 转发。
    自建服务: base_url 指向你的网关(如 one-api / new-api / vllm / 自建),
    api_key 为空时也可匿名调用(部分本地服务不需要 key)。
    """

    name = "openai"
    cloud = True

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "whisper-1") -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model or "whisper-1"

    def available(self) -> bool:
        # 空 base_url = 官方,必须有 key;自建网关(base_url 非官方)才允许匿名
        if self.base_url == "https://api.openai.com/v1":
            return bool(self.api_key)
        return bool(self.base_url)

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def transcribe_file(self, audio: bytes, filename: str = "audio.wav") -> str:
        """把上传的音频转发给 OpenAI 兼容转录接口,返回纯文本。"""
        try:
            import httpx
        except Exception as e:
            raise STTProviderError(f"httpx 未安装: {e}") from e

        url = f"{self.base_url}/audio/transcriptions"
        files = {"file": (filename, audio, "audio/wav" if filename.endswith(".wav") else "audio/webm")}
        data = {"model": self.model}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=self._headers(), files=files, data=data)
        except Exception as e:
            raise STTProviderError(f"OpenAI 转录请求失败: {e}") from e
        if r.status_code != 200:
            raise STTProviderError(f"OpenAI 转录返回 {r.status_code}: {r.text[:300]}")
        try:
            payload = r.json()
        except Exception:
            raise STTProviderError("OpenAI 转录返回非 JSON")
        text = payload.get("text") or payload.get("choices", [{}])[0].get("text") or ""
        return text.strip()

    # 流式接口保持“未接入”占位;文件式由 /voice/stt/upload 直接调 transcribe_file
    async def start_stream(self, on_result: OnResult) -> None:
        raise STTProviderError("OpenAI 兼容引擎为文件式接口,请用前端录音上传(已自动处理)")


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

    enabled: bool = True
    priority: list[str] = field(default_factory=lambda: ["sensevoice"])
    language: str = "auto"
    threads: int = 4
    use_vad: bool = True
    chunk_size: int = 100
    min_mute_chunks: int = 10
    max_nomute_chunks: int = 80
    use_prefix: bool = True        # sensevoice 补充语种/情感/事件信息
    use_itn: bool = True           # 逆文本正则化(补标点)
    capture_device: int = -1       # -1 = 默认麦克风
    no_gpu: bool = False
    flash_attn: bool = False
    # 云端凭据(OpenAI 兼容文件式接口)
    openai_api_key: str = ""
    openai_base_url: str = ""        # 空 = 官方 https://api.openai.com/v1
    openai_model: str = "whisper-1"
    # 兼容占位(保留但不再用于流式)
    funasr_ws_url: str = ""
    xfyun_app_id: str = ""
    xfyun_api_key: str = ""
    xfyun_api_secret: str = ""

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "priority": list(self.priority),
            "language": self.language,
            "threads": self.threads,
            "use_vad": self.use_vad,
            "chunk_size": self.chunk_size,
            "min_mute_chunks": self.min_mute_chunks,
            "max_nomute_chunks": self.max_nomute_chunks,
            "use_prefix": self.use_prefix,
            "use_itn": self.use_itn,
            "capture_device": self.capture_device,
            "no_gpu": self.no_gpu,
            "flash_attn": self.flash_attn,
            "openai_api_key": self.openai_api_key,
            "openai_base_url": self.openai_base_url,
            "openai_model": self.openai_model,
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
            return SenseVoiceProvider(
                language=cfg.language,
                threads=cfg.threads,
                use_vad=cfg.use_vad,
                chunk_size=cfg.chunk_size,
                min_mute_chunks=cfg.min_mute_chunks,
                max_nomute_chunks=cfg.max_nomute_chunks,
                use_prefix=cfg.use_prefix,
                use_itn=cfg.use_itn,
                capture_device=cfg.capture_device,
                no_gpu=cfg.no_gpu,
                flash_attn=cfg.flash_attn,
            )
        if name == FunASRCloudProvider.name:
            return FunASRCloudProvider(ws_url=cfg.funasr_ws_url)
        if name == OpenAIWhisperStreamProvider.name:
            return OpenAIWhisperStreamProvider(
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                model=cfg.openai_model,
            )
        if name == XfyunProvider.name:
            return XfyunProvider(app_id=cfg.xfyun_app_id, api_key=cfg.xfyun_api_key, api_secret=cfg.xfyun_api_secret)
        raise STTProviderError(f"未知 STT 引擎: {name}")

    def status(self) -> dict:
        out = {}
        for name, cls in PROVIDER_CLASSES.items():
            if cls is SenseVoiceProvider:
                inst = cls()
            else:
                # 云端 provider 需要配置参数,用当前配置构造(否则 available 恒 false)
                inst = self._build_provider(name)
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
