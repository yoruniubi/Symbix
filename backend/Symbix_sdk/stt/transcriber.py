from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional
from Symbix_sdk.resource_path import stt_bin_dir, stt_model_dir

class STTProviderError(Exception):
    """单个 provider 失败(引擎会捕获并尝试下一个)。"""

OnResult = Callable[[str], Awaitable[None]]

# ---------------- stream 输出解析(纯函数,可单测) ----------------

# 识别帧:[0.60-1.70]<|en|><|EMO_UNKNOWN|><|Speech|><|withitn|>文本
_FRAME_RE = re.compile(r"\[(\d+\.\d+)-(\d+\.\d+)\]")
_META_RE = re.compile(r"<\|[^>]*?\|>")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def parse_stream_frame(raw: str) -> Optional[tuple[float, float, str]]:
    """把一帧原始输出解析成 (start_sec, end_sec, 纯文本)。

    stream.exe 的识别帧形如:
        [0.60-1.70]<|en|><|EMO_UNKNOWN|><|Speech|><|withitn|>你好世界
    帧间用 \r 分隔,还夹着 ANSI 清屏转义([2K)与空格填充。
    非识别帧(init:/model_load 等)返回 None。
    """
    text = _ANSI_RE.sub("", raw).strip()
    if not text:
        return None
    m = _FRAME_RE.search(text)
    if not m:
        return None  # init/model_load 等日志行
    start, end = float(m.group(1)), float(m.group(2))
    body = _META_RE.sub("", text[m.end():]).strip()
    return (start, end, body)


class StreamSegmentAggregator:
    """把 stream.exe 的刷新帧流聚合成"一句一结果"。

    同一 VAD 段内,exe 会反复刷新同一句(起点固定、终点递增);
    起点回退(新段开始)或静默超时 → 上一段成句,回调最终文本。
    """

    def __init__(self, flush_idle: float = 0.8) -> None:
        self.flush_idle = flush_idle   # 距上一帧超过该秒数视为段落结束
        self._seg_start: Optional[float] = None
        self._seg_end: Optional[float] = None
        self._seg_text = ""
        self._last_ts: Optional[float] = None  # 最近帧的 end_sec(用于静默判定)

    def feed(self, start: float, end: float, text: str) -> Optional[str]:
        """喂入一帧;段落成句时返回最终文本,否则返回 None。"""
        finalized: Optional[str] = None
        new_segment = (
            self._seg_start is not None and start < self._seg_start
        ) or (
            self._last_ts is not None and start - self._last_ts > self.flush_idle
        )
        if new_segment and self._seg_text:
            finalized = self._seg_text
            self._seg_start = None
            self._seg_end = None
            self._seg_text = ""
        if self._seg_start is None:
            self._seg_start = start
        if end >= (self._seg_end or 0.0):
            self._seg_end = end
            self._seg_text = text  # 同段内取终点最靠后的刷新(最完整)
        self._last_ts = end
        return finalized

    def flush(self) -> Optional[str]:
        """主动冲刷当前未成句的段落(流结束/停止时调用)。"""
        text = self._seg_text
        self._seg_start = None
        self._seg_end = None
        self._seg_text = ""
        self._last_ts = None
        return text or None


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
        self._stderr_task: Optional[asyncio.Task] = None

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

    # ---- 设备枚举 ----
    async def list_devices(self) -> list[dict]:
        """枚举本机音频捕获设备(供设置页下拉选择麦克风)。

        原理:stream 版 exe 启动时会在 stdout 打印设备清单,
        随后才打开默认/指定设备。这里短启进程读到清单后立即终止,
        不真正进入录音循环。返回 [{"id": int, "name": str}, ...]。
        """
        import re

        bin_ = self._resolve_binary()
        if not bin_ or "stream" not in bin_.lower():
            # 非 stream 版(纯文件转写)不支持设备枚举/实时捕获
            return []
        model = self._resolve_model()
        if not model:
            return []
        devices: list[dict] = []
        pattern = re.compile(r"Capture device #(\d+): '(.*?)'")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = await asyncio.create_subprocess_exec(
                bin_, "-m", model, "-l", self.language,
                # 设备清单打在 stderr(与识别结果的 stdout 分离)
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
                # cwd=bin 目录:让 exe 的特征缓存(fbank_lfr_cmvn_feature.json)
                # 落在 stt/bin 而非进程工作目录(backend 根)
                cwd=stt_bin_dir(),
            )
        except Exception as e:
            raise STTProviderError(f"SenseVoice 枚举设备失败: {e}") from e
        try:
            assert proc.stderr
            # 读到设备清单(通常 3~5 行)或超时则终止,不进入录音循环
            err = proc.stderr
            for _ in range(40):
                try:
                    raw = await asyncio.wait_for(err.readline(), timeout=2.0)
                except asyncio.TimeoutError:
                    break
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace")
                m = pattern.search(line)
                if m:
                    devices.append({"id": int(m.group(1)), "name": m.group(2).strip()})
                # 开始打开设备/加载模型 = 设备清单已结束,不用再等
                if "attempt to open" in line.lower() or "loading model" in line.lower():
                    break
        finally:
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.kill()
            except (ProcessLookupError, OSError):
                pass
        return devices

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
                "--chunk-size", str(self.chunk_size),
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
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
                # cwd=bin 目录:特征缓存(fbank_lfr_cmvn_feature.json)
                # 写在 stt/bin,dll 也在该目录,避免污染 backend 根
                cwd=stt_bin_dir(),
            )
        except Exception as e:
            raise STTProviderError(f"SenseVoice 启动失败: {e}") from e

        async def _drain_stderr() -> None:
            # 把 exe 的 stderr(设备枚举/模型加载/报错)打进后端日志,便于诊断
            assert self._process and self._process.stderr
            try:
                while True:
                    line = await self._process.stderr.readline()
                    if not line:
                        break
                    print("[stt]", line.decode("utf-8", errors="replace").rstrip(), flush=True)
            except Exception:
                pass

        self._stderr_task = asyncio.create_task(_drain_stderr())

        async def _pump() -> None:
            assert self._process and self._process.stdout
            # stream.exe 的识别帧用 \r 分隔(同行刷新),整段结束才有 \n;
            # readline 会卡到整段结束且拿到的是带 ANSI/元数据的脏文本。
            # 这里按块读 + 双分隔符切帧,经解析/聚合后只回调成句文本。
            agg = StreamSegmentAggregator()
            buf = ""
            stdout = self._process.stdout
            while True:
                chunk = await stdout.read(256)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="replace")
                # \r 与 \n 都是帧边界
                while True:
                    idx = min(
                        (p for p in (buf.find("\r"), buf.find("\n")) if p != -1),
                        default=-1,
                    )
                    if idx == -1:
                        break
                    frame, buf = buf[:idx], buf[idx + 1:]
                    parsed = parse_stream_frame(frame)
                    if not parsed:
                        continue
                    start, end, text = parsed
                    if not text:
                        continue
                    finalized = agg.feed(start, end, text)
                    if finalized:
                        try:
                            await on_result(finalized)
                        except Exception:
                            pass
            # 进程退出:冲刷最后一段,并打印退出码便于诊断秒退
            rc = self._process.returncode if self._process else None
            if rc is not None and rc != 0:
                print(f"[stt] sense-voice-stream exited rc={rc}", flush=True)
            tail = agg.flush()
            if tail:
                try:
                    await on_result(tail)
                except Exception:
                    pass

        self._reader_task = asyncio.create_task(_pump())

    def stop(self) -> None:
        for t in (self._reader_task, self._stderr_task):
            if t:
                t.cancel()
        self._reader_task = None
        self._stderr_task = None
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
        self._process = None


# ---------------- 云端(OpenAI 兼容文件式接口) ----------------

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


# ---------------- 注册表 + 引擎 ----------------

PROVIDER_CLASSES: dict[str, type[STTProvider]] = {
    SenseVoiceProvider.name: SenseVoiceProvider,
    OpenAIWhisperStreamProvider.name: OpenAIWhisperStreamProvider,
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
        if name == OpenAIWhisperStreamProvider.name:
            return OpenAIWhisperStreamProvider(
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                model=cfg.openai_model,
            )
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
