from __future__ import annotations

import json
import os
import threading
from Symbix_sdk.tts.synthesizer import TTSConfig
from Symbix_sdk.stt.transcriber import STTConfig

_lock = threading.Lock()


class VoiceConfigManager:
    def __init__(self, path: str) -> None:
        self.path = path
        self.tts = TTSConfig()
        self.stt = STTConfig()
        self._load()

    # ---- io ----
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in (raw.get("tts") or {}).items():
                if hasattr(self.tts, k):
                    setattr(self.tts, k, v)
            for k, v in (raw.get("stt") or {}).items():
                if hasattr(self.stt, k):
                    setattr(self.stt, k, v)
        except Exception as e:
            print(f"[voice] 配置读取失败(用默认值): {e}")

    def save(self) -> None:
        with _lock:
            data = {"tts": self.tts.to_dict(), "stt": self.stt.to_dict()}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def apply_tts_patch(self, patch: dict) -> None:
        """部分更新 TTS 配置(priority/voice_*/speed/openai_*)。"""
        allowed = set(TTSConfig().to_dict().keys())
        for k, v in (patch or {}).items():
            if k in allowed and v is not None:
                setattr(self.tts, k, v)
        self.save()

    def apply_stt_patch(self, patch: dict) -> None:
        allowed = set(STTConfig().to_dict().keys())
        for k, v in (patch or {}).items():
            if k in allowed and v is not None:
                setattr(self.stt, k, v)
        self.save()
