from __future__ import annotations
import asyncio
import re
import time
from dataclasses import dataclass, field
from Symbix_sdk.tts import edge_update

# 朗读前需要剔除的 emoji/装饰符号区间(保留普通文本与 CJK 标点)。
# 覆盖:emoji 主体、杂项符号、交通/几何/箭头扩展、旗标、变体选择符 VS16、
# ZWJ 零宽连接符与 keycap 围音符(数字 emoji 如 1️⃣ 会保留数字、去掉修饰)。
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # 区域指示符(国旗/地区旗)
    "\U0001F300-\U0001F64F"  # 杂项符号与表情主体
    "\U0001F680-\U0001F6FF"  # 交通与地图符号
    "\U0001F700-\U0001F77F"  # 炼金术/几何扩展
    "\U0001F780-\U0001F8FF"  # 几何图形与补充箭头
    "\U0001F900-\U0001F9FF"  # 补充符号与象形文字
    "\U0001FA00-\U0001FAFF"  # 象形文字扩展 A/B
    "\U00002600-\U000026FF"  # 杂项符号(☀ ♠ …)
    "\U00002700-\U000027BF"  # 装饰符号(✂ ✈ …)
    "\U0000FE0F"             # 变体选择符 VS16
    "\U0000200D"             # ZWJ 零宽连接符
    "\U000020E3"             # keycap 围音符
    "]+",
    re.UNICODE,
)


def strip_emoji(text: str) -> str:
    """去掉字符串中的 emoji/装饰符号,供 TTS 朗读前清洗。

    返回纯文本;输入为 None/空串时原样返回空串。
    """
    return _EMOJI_RE.sub("", text or "")


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

def _is_sec_token_403(e: Exception) -> bool:
    """判定是否「微软轮换了 Sec-MS-GEC 令牌代次」导致的 403(升库就能解)。

    靠 URL 里的 Sec-MS-GEC 字样把这类 403 和普通的鉴权/封 IP 区分开。
    """
    msg = str(e)
    return "403" in msg and "Sec-MS-GEC" in msg


def _edge_error_hint(e: Exception) -> str:
    """把 edge-tts 的报错翻译成用户能动手解决的话。

    最常见的一种:微软周期性轮换 Sec-MS-GEC token 方案(如 2025-10 把 v1 的纯
    SHA256 换成 v2 的 CS64+SHA256),旧版 edge-tts 一律在 WSS 握手阶段被 403 拒。
    此时不是网络/代理/配置问题,唯一解法是升级库 —— 直接把话说到位。
    """
    msg = str(e)
    if "403" not in msg:
        return f"Edge 合成失败: {msg}"

    ver = "未知"
    try:
        import edge_tts
        ver = getattr(edge_tts, "__version__", "未知")
    except Exception:
        pass
    return (
        f"Edge 合成失败: 403 —— 微软拒绝了 Sec-MS-GEC 令牌校验。"
        f"当前 edge-tts {ver},通常是版本过旧(微软会周期性更换令牌代次)。"
        f"升级即可恢复:pip install -U edge-tts 并重启后端。"
        f"原始报错: {msg}"
    )


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
            raise TTSProviderError(_edge_error_hint(e)) from e

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


# ---------------- 自定义 HTTP GET 语音服务 ----------------

def parse_custom_servers(raw: str) -> list[str]:
    """拆自定义 TTS 地址(每行一个),忽略空行/注释行与非 http(s) 的行。"""
    out: list[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if not s.lower().startswith(("http://", "https://")):
            continue
        out.append(s.rstrip("/"))
    return out


class CustomHTTPProvider(TTSProvider):
    """自定义 HTTP TTS:GET {server}?text=..&speaker=..&speed=..

    适配 GPT-SoVITS / Bert-VITS2 等本地一键包(GET 请求直接返回音频字节)。
    地址支持多行(每行一个),按调用次数轮询,便于多个实例分担请求。
    """

    name = "custom"
    cloud = False  # 本地/自建服务,设置页与 edge 同类展示

    def __init__(self, servers: str = "") -> None:
        self.servers = parse_custom_servers(servers)
        self._rr = 0

    def available(self) -> bool:
        return bool(self.servers)

    def voices(self) -> list[dict]:
        # speaker 由用户手填(各服务命名差异太大),没有可枚举的音色表
        return []

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0) -> TTSResult:
        try:
            import httpx
        except Exception as e:
            raise TTSProviderError(f"httpx 未安装: {e}") from e

        server = self.servers[self._rr % len(self.servers)]
        self._rr = (self._rr + 1) % len(self.servers)
        params: dict[str, object] = {
            "text": text,
            "speed": max(0.25, min(4.0, float(speed))),
        }
        if voice:
            params["speaker"] = voice
        try:
            # trust_env=False:自建/本地服务不应走系统代理(否则 127.0.0.1 会被代理拦成 502)
            async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
                r = await client.get(server, params=params)
        except Exception as e:
            raise TTSProviderError(f"自定义 TTS 连接失败({server}): {e}") from e
        if r.status_code != 200:
            raise TTSProviderError(f"自定义 TTS 返回 {r.status_code}: {r.text[:300]}")
        audio = r.content
        if not audio:
            raise TTSProviderError("自定义 TTS 返回空音频")
        # 依 Content-Type 猜格式(自定义服务多数返回 wav,少数 mp3)
        ctype = r.headers.get("content-type", "").lower()
        if "mpeg" in ctype or "mp3" in ctype or audio[:3] == b"ID3":
            fmt = "mp3"
        elif "wav" in ctype or audio[:4] == b"RIFF" or audio[:4] == b"OggS":
            fmt = "wav"
        else:
            fmt = "wav"
        return TTSResult(audio=audio, format=fmt, engine=self.name)


# ---------------- 注册表 + 引擎 ----------------

PROVIDER_CLASSES: dict[str, type[TTSProvider]] = {
    EdgeProvider.name: EdgeProvider,
    OpenAICompatTTSProvider.name: OpenAICompatTTSProvider,
    CustomHTTPProvider.name: CustomHTTPProvider,
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
    # 自定义 HTTP GET 服务(GPT-SoVITS / Bert-VITS2 …)
    voice_custom: str = ""        # speaker 名;空 = 不传该参数
    custom_servers: str = ""      # 多行文本,每行一个地址;按调用次数轮询
    # edge 遇到 403(微软换令牌代次)时自动升级 edge-tts 并重试一次
    edge_auto_update: bool = True

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
            "voice_custom": self.voice_custom,
            "custom_servers": self.custom_servers,
            "edge_auto_update": self.edge_auto_update,
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
            elif cls is CustomHTTPProvider:
                self._instances[name] = cls(servers=self.config.custom_servers)
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
        # 过滤 emoji/装饰符号:edge-tts/OpenAI TTS 读不了这些,且会拖慢/报错
        text = strip_emoji(text).strip()
        if not text:
            raise TTSProviderError("text 为空(过滤 emoji 后无可朗读内容)")
        # 指定试听引擎:只用这一个,不降级
        order = [engine] if engine else list(cfg.priority)
        for name in order:
            voice = ""
            try:
                p = self._provider(name)
                if not p.available():
                    errors.append(f"{name}: 不可用(未配置或依赖缺失)")
                    continue
                voice = getattr(cfg, f"voice_{name}", "") or ""
                return await p.synthesize(text, voice=voice, speed=cfg.speed)
            except TTSProviderError as e:
                healed = await self._edge_selfheal(name, text, voice, e)
                if isinstance(healed, TTSResult):
                    return healed
                errors.append(healed or f"{name}: {e}")
        raise TTSProviderError("所有 TTS 引擎均失败 → " + "; ".join(errors))

    async def _edge_selfheal(
        self, name: str, text: str, voice: str, err: TTSProviderError
    ) -> TTSResult | str | None:
        """edge 的 403 自愈:升库 → 清模块缓存 → 重试一次。

        返回 `TTSResult` = 自愈成功;返回 `str` = 自愈过但仍失败(当作错误文案);
        返回 `None` = 不该自愈,交给上层用原报错。
        """
        if name != EdgeProvider.name or not self.config.edge_auto_update:
            return None
        if not _is_sec_token_403(err):
            return None

        # pip 可能跑几十秒,丢线程池,别堵事件循环
        ok, detail = await asyncio.to_thread(edge_update.upgrade)
        if not ok:
            return f"{name}: {err}(自动升级 edge-tts 失败:{detail})"

        # 必须清缓存:edge_tts 是 lazy import,不清的话进程里还是旧代码
        edge_update.reload_modules()
        self.reload()
        try:
            p = self._provider(name)
            return await p.synthesize(text, voice=voice, speed=self.config.speed)
        except TTSProviderError as e2:
            return f"{name}: 已自动升级 edge-tts({detail}),但仍失败 → {e2}"

tts_engine = TTSEngine()
