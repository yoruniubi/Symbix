# backend/Symbix_sdk/stt/sensevoice_cpp.py
import asyncio
import subprocess
from pathlib import Path
# from .base import STTProvider

# 使用sense-voice-small-q4_k模型，性能和准确率都不错，适合实时识别
class SenseVoiceCppProvider():
    def __init__(
        self,
        binary_path: str = "bin/sense-voice-stream",
        model_path: str = "models/sense-voice-small-q4_k.gguf",
        language: str = "auto",
        threads: int = 4,
        use_vad: bool = True,
    ):
        self.binary_path = Path(binary_path)
        self.model_path = model_path
        self.language = language
        self.threads = threads
        self.use_vad = use_vad
        self._process: subprocess.Popen | None = None

    def _build_cmd(self) -> list[str]:
        cmd = [
            str(self.binary_path),
            "-m", self.model_path,
            "-l", self.language,
            "-t", str(self.threads),
        ]
        if self.use_vad:
            cmd.append("--use-vad")
        return cmd

    async def start_stream(self, on_result):
        """
        启动实时麦克风识别，on_result 是回调函数，每识别出一句话就调用
        on_result(text: str)
        """
        cmd = self._build_cmd()
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async for line in self._process.stdout:
            text = line.decode("utf-8").strip()
            if text:
                await on_result(text)

    def stop(self):
        if self._process and self._process.returncode is None:
            self._process.terminate()
            self._process = None

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """非流式接口，用于录制好的音频片段识别（暂时不实现）"""
        raise NotImplementedError("SenseVoice.cpp 目前只支持实时流式")