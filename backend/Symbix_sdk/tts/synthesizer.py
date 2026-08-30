from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from Symbix_sdk.resource_path import tts_model_dir


@dataclass
class TTSResult:
    """合成结果:音频字节 + 便于前端 <audio> 播放的 mime 类型。"""

    audio: bytes
    format: str  # "wav" | "mp3"
    engine: str  # 实际命中的 provider 名,便于前端提示

    @property
    def mime(self) -> str:
        return "audio/wav" if self.format == "wav" else "audio/mpeg"


class TTSProviderError(Exception):
    """单个 provider 失败(引擎会捕获并尝试下一个)。"""


class TTSProvider:
    """子类实现 name 与 _synthesize;available() 用于快速探测可用性。"""

    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def voices(self) -> list[dict]:
        """返回该引擎可用的音色列表 [{value,label}]。"""
        return []

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> TTSResult:
        raise NotImplementedError


# ---------------- Piper(本地主) ----------------

class PiperProvider(TTSProvider):
    """piper-tts Python API;模型目录 tts/model/*.onnx(+.json 同名配对)。"""

    name = "piper"

    def __init__(self) -> None:
        self._voices_cache: Optional[list[dict]] = None

    def available(self) -> bool:
        try:
            import piper  # noqa: F401
        except Exception:
            return False
        return len(self.list_models()) > 0

    def list_models(self) -> list[Path]:
        d = tts_model_dir()
        if not d.exists():
            return []
        return sorted(d.glob("*.onnx"))

    def voices(self) -> list[dict]:
        if self._voices_cache is not None:
            return self._voices_cache
        out = []
        for p in self.list_models():
            label = p.stem.replace("_", " ")
            out.append({"value": str(p), "label": label})
        self._voices_cache = out
        return out

    def _load_voice(self, model_path: str):
        from piper import PiperVoice  # 延迟导入,没装包时不影响其它引擎

        return PiperVoice.load(model_path)

    @staticmethod
    def _bytes_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, width: int = 2) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(sample_rate)
            w.writeframes(pcm)
        return buf.getvalue()

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> TTSResult:
        import asyncio

        models = self.list_models()
        if not models:
            raise TTSProviderError("Piper: tts/model 下没有 .onnx 模型")
        model_path = voice if voice and Path(voice).suffix == ".onnx" else str(models[0])
        length_scale = max(0.1, 1.0 / max(0.1, speed))  # speed>1 → 语速快

        def _run() -> bytes:
            v = self._load_voice(model_path)
            sink = io.BytesIO()
            with wave.open(sink, "wb") as wav_file:
                # 不同 piper-tts 版本签名不同:新版支持 syn_config/length_scale,
                # 旧版只收 (text, wav_file)。逐级回退保证兼容。
                try:
                    v.synthesize_wav(text, wav_file, length_scale=length_scale)
                except TypeError:
                    try:
                        from piper.config import SynthesisConfig  # type: ignore
                        cfg = SynthesisConfig(length_scale=length_scale)
                        v.synthesize_wav(text, wav_file, syn_config=cfg)
                    except Exception:
                        v.synthesize_wav(text, wav_file)
            return sink.getvalue()

        try:
            # piper 合成是 CPU 密集,丢线程池避免卡事件循环
            audio = await asyncio.to_thread(_run)
        except Exception as e:
            raise TTSProviderError(f"Piper 合成失败: {e}") from e
        return TTSResult(audio=audio, format="wav", engine=self.name)


# ---------------- Edge(云端辅) ----------------

class EdgeProvider(TTSProvider):
    """edge-tts:微软免费接口,输出 mp3。voice 形如 zh-CN-XiaoxiaoNeural。"""

    name = "edge"

    PRESET_VOICES = [
        {"value": "zh-CN-XiaoxiaoNeural", "label": "晓晓 (女·普通话)"},
        {"value": "zh-CN-YunxiNeural", "label": "云希 (男·普通话)"},
        {"value": "zh-CN-YunyangNeural", "label": "云扬 (男·新闻)"},
        {"value": "zh-HK-HiuMaanNeural", "label": "曉曼 (女·粤语)"},
        {"value": "en-US-AriaNeural", "label": "Aria (Female·EN)"},
        {"value": "en-US-GuyNeural", "label": "Guy (Male·EN)"},
        {"value": "ja-JP-NanamiNeural", "label": "七海 (女·日本語)"},
    ]

    def available(self) -> bool:
        try:
            import edge_tts  
            return True
        except Exception:
            return False

    def voices(self) -> list[dict]:
        return list(self.PRESET_VOICES)

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> TTSResult:
        try:
            import edge_tts
        except Exception as e:
            raise TTSProviderError("edge-tts 未安装 (pip install edge-tts)") from e

        chosen = voice or self.PRESET_VOICES[0]["value"]
        # edge-tts 的 rate 是 "+10%" / "-20%" 百分比字符串
        percent = int(round((speed - 1.0) * 100))
        rate = f"{percent:+d}%"

        try:
            communicate = edge_tts.Communicate(text, chosen, rate=rate)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
        except Exception as e:
            raise TTSProviderError(f"Edge 合成失败: {e}") from e

        audio = b"".join(chunks)
        if not audio:
            raise TTSProviderError("Edge 返回空音频")
        return TTSResult(audio=audio, format="mp3", engine=self.name)


# ---------------- 注册表 + 引擎 ----------------

PROVIDER_CLASSES: dict[str, type[TTSProvider]] = {
    PiperProvider.name: PiperProvider,
    EdgeProvider.name: EdgeProvider,
}


@dataclass
class TTSConfig:
    """用户手动配置:优先级从高到低 + 各引擎默认音色/语速。"""

    priority: list[str] = field(default_factory=lambda: ["piper", "edge"])
    voice_piper: str = ""          # 空 = 取 model 目录第一个 onnx
    voice_edge: str = "zh-CN-XiaoxiaoNeural"
    speed: float = 1.0

    def to_dict(self) -> dict:
        return {
            "priority": list(self.priority),
            "voice_piper": self.voice_piper,
            "voice_edge": self.voice_edge,
            "speed": self.speed,
        }


class TTSEngine:
    """按手动优先级依次尝试,全部失败才抛错。"""

    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self._instances: dict[str, TTSProvider] = {}

    def _provider(self, name: str) -> TTSProvider:
        if name not in self._instances:
            cls = PROVIDER_CLASSES.get(name)
            if cls is None:
                raise TTSProviderError(f"未知 TTS 引擎: {name}")
            self._instances[name] = cls()
        return self._instances[name]

    def status(self) -> dict:
        """给设置页展示:每个引擎可用性 + 音色列表。"""
        out = {}
        for name in PROVIDER_CLASSES:
            p = self._provider(name)
            out[name] = {
                "available": p.available(),
                "voices": p.voices(),
            }
        return out

    async def synthesize(self, text: str, engine: str | None = None) -> TTSResult:
        cfg = self.config
        errors: list[str] = []
        # 指定试听引擎:只用这一个,不降级
        order = [engine] if engine else list(cfg.priority)
        for name in order:
            try:
                p = self._provider(name)
                if not p.available():
                    errors.append(f"{name}: 不可用(未安装或缺模型)")
                    continue
                voice = getattr(cfg, f"voice_{name}", "") or ""
                return await p.synthesize(text, voice=voice, speed=cfg.speed)
            except TTSProviderError as e:
                errors.append(f"{name}: {e}")
        raise TTSProviderError("所有 TTS 引擎均失败 → " + "; ".join(errors))


# 全局单例(state.py 引用)
tts_engine = TTSEngine()
