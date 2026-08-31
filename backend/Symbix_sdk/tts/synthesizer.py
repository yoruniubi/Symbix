from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


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

    # 精简版只保留中日英:中文全部 + 日文全部 + 英文白名单男女各二
    _KEEP_LOCALES = ("zh", "ja")
    _KEEP_EN = {
        "en-US-AriaNeural", "en-US-GuyNeural",       # 美式男女
        "en-GB-LibbyNeural", "en-GB-ThomasNeural",   # 英式男女
    }
    # 中文/日文音色的友好中文名(其余语言保留原名)
    _NAME_ZH = {
        "zh-CN-XiaoxiaoNeural": "晓晓", "zh-CN-XiaoyiNeural": "晓伊",
        "zh-CN-YunjianNeural": "云健", "zh-CN-YunxiNeural": "云希",
        "zh-CN-YunxiaNeural": "云夏", "zh-CN-YunyangNeural": "云扬",
        "zh-CN-liaoning-XiaobeiNeural": "小北 (东北话)",
        "zh-CN-shaanxi-XiaoniNeural": "小妮 (陕西话)",
        "zh-TW-HsiaoChenNeural": "曉臻", "zh-TW-HsiaoYuNeural": "曉雨",
        "zh-TW-YunJheNeural": "雲哲",
        "zh-HK-HiuGaaiNeural": "曉佳 (粤语)", "zh-HK-HiuMaanNeural": "曉曼 (粤语)",
        "zh-HK-WanLungNeural": "雲龍 (粤语)",
        "ja-JP-KeitaNeural": "慶太", "ja-JP-NanamiNeural": "七海",
        "en-US-AriaNeural": "Aria (美式)", "en-US-GuyNeural": "Guy (美式)",
        "en-GB-LibbyNeural": "Libby (英式)", "en-GB-ThomasNeural": "Thomas (英式)",
    }

    def available(self) -> bool:
        try:
            import edge_tts  
            return True
        except Exception:
            return False

    def voices(self) -> list[dict]:
        return list(self.PRESET_VOICES)

    # 类级缓存:1 小时内不重复拉取 edge 全量音色表
    _cache_ts: float = 0.0
    _cache: list[dict] = []
    _cache_ttl = 3600.0

    async def voices_async(self) -> list[dict]:
        """动态拉取 edge-tts 音色,精简为中日英;网络失败回落常用预设。"""
        now = time.time()
        if self._cache and now - self._cache_ts < self._cache_ttl:
            return list(self._cache)
        try:
            import edge_tts
            vs = await edge_tts.list_voices()
        except Exception:
            return list(self.PRESET_VOICES)  # 离线/网络失败:回落预设
        out = []
        gender_zh = {"Male": "男", "Female": "女"}
        for v in vs:
            short = v.get("ShortName") or ""
            if not short:
                continue
            loc = v.get("Locale") or ""
            # 只保留中文/日文全部 + 英文白名单
            if loc.startswith(self._KEEP_LOCALES):
                pass
            elif short in self._KEEP_EN:
                pass
            else:
                continue
            gender = v.get("Gender") or ""
            cname = self._NAME_ZH.get(short)
            if cname:
                label = cname
                if gender in gender_zh:
                    label = f"{label} ({gender_zh[gender]})"
            else:
                # 中文/日文但没映射到的,退回友好名
                friendly = v.get("FriendlyName") or ""
                label = friendly.replace("Microsoft ", "").replace(" Online", "")
            out.append({"value": short, "label": label})
        # 排序:中文在前 → 日文 → 英文;组内按音色名
        def _k(x: dict):
            v = x["value"]
            grp = 0 if v.startswith("zh") else (1 if v.startswith("ja") else 2)
            return (grp, v)
        out.sort(key=_k, reverse=False)
        self._cache = out
        self._cache_ts = now
        return list(out)

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


# ---------------- OpenAI 兼容云端(自建网关/中转) ----------------

class OpenAICompatTTSProvider(TTSProvider):
    """OpenAI 兼容 POST {base_url}/audio/speech。

    适用于自建中转/网关(one-api / new-api / vllm / 自建 TTS 服务),
    只要实现 OpenAI 同款接口即可。用 httpx 直调,不依赖 openai SDK。
    """

    name = "openai"
    cloud = True

    PRESET_VOICES = [
        {"value": "alloy", "label": "alloy"},
        {"value": "echo", "label": "echo"},
        {"value": "fable", "label": "fable"},
        {"value": "onyx", "label": "onyx"},
        {"value": "nova", "label": "nova"},
        {"value": "shimmer", "label": "shimmer"},
        {"value": "ash", "label": "ash"},
        {"value": "coral", "label": "coral"},
        {"value": "sage", "label": "sage"},
        {"value": "verse", "label": "verse"},
        {"value": "ballad", "label": "ballad"},
    ]

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "tts-1") -> None:
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model or "tts-1"

    def available(self) -> bool:
        # 配了 base_url 即视为可用(匿名自建服务也可以);官方则必须有 key
        if self.base_url == "https://api.openai.com/v1":
            return bool(self.api_key)
        return bool(self.base_url)

    def voices(self) -> list[dict]:
        return list(self.PRESET_VOICES)

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> TTSResult:
        try:
            import httpx
        except Exception as e:
            raise TTSProviderError(f"httpx 未安装: {e}") from e

        url = f"{self.base_url}/audio/speech"
        headers = {"Accept": "audio/*"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "input": text,
            "voice": voice or "alloy",
            "speed": max(0.25, min(4.0, float(speed))),
            "response_format": "mp3",
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=headers, json=body)
        except Exception as e:
            raise TTSProviderError(f"OpenAI TTS 请求失败: {e}") from e
        if r.status_code != 200:
            raise TTSProviderError(f"OpenAI TTS 返回 {r.status_code}: {r.text[:300]}")
        audio = r.content
        if not audio:
            raise TTSProviderError("OpenAI TTS 返回空音频")
        # 多数服务返回 mp3;个别返回 wav。按 Content-Type 判断格式
        ctype = r.headers.get("content-type", "")
        fmt = "wav" if ("wav" in ctype or audio[:4] == b"RIFF") else "mp3"
        return TTSResult(audio=audio, format=fmt, engine=self.name)


# ---------------- 注册表 + 引擎 ----------------

PROVIDER_CLASSES: dict[str, type[TTSProvider]] = {
    EdgeProvider.name: EdgeProvider,
    OpenAICompatTTSProvider.name: OpenAICompatTTSProvider,
}


@dataclass
class TTSConfig:
    """用户手动配置:优先级从高到低 + 各引擎默认音色/语速。"""

    enabled: bool = True
    priority: list[str] = field(default_factory=lambda: ["edge"])
    voice_edge: str = "zh-CN-XiaoxiaoNeural"
    speed: float = 1.0
    # OpenAI 兼容云端(自建网关/中转)
    voice_openai: str = "alloy"
    openai_api_key: str = ""
    openai_base_url: str = ""     # 空 = 官方 https://api.openai.com/v1
    openai_model: str = "tts-1"

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "priority": list(self.priority),
            "voice_edge": self.voice_edge,
            "speed": self.speed,
            "voice_openai": self.voice_openai,
            "openai_api_key": self.openai_api_key,
            "openai_base_url": self.openai_base_url,
            "openai_model": self.openai_model,
        }


class TTSEngine:
    """按手动优先级依次尝试,全部失败才抛错。"""

    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self._instances: dict[str, TTSProvider] = {}

    def reload(self) -> None:
        """配置热更新后清空缓存的 provider,下次按新配置重建。"""
        self._instances = {}

    def _provider(self, name: str) -> TTSProvider:
        if name not in self._instances:
            cls = PROVIDER_CLASSES.get(name)
            if cls is None:
                raise TTSProviderError(f"未知 TTS 引擎: {name}")
            if cls is OpenAICompatTTSProvider:
                self._instances[name] = cls(
                    api_key=self.config.openai_api_key,
                    base_url=self.config.openai_base_url,
                    model=self.config.openai_model,
                )
            else:
                self._instances[name] = cls()
        return self._instances[name]

    async def status(self) -> dict:
        """给设置页展示:每个引擎可用性 + 音色列表(支持异步拉取)。"""
        out = {}
        for name in PROVIDER_CLASSES:
            p = self._provider(name)
            va = getattr(p, "voices_async", None)
            voices = await va() if callable(va) else p.voices()
            out[name] = {
                "available": p.available(),
                "voices": voices,
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
