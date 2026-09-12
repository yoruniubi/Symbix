import json
import os
from dataclasses import dataclass, asdict

@dataclass
class AppConfig:
    personality: str = "活泼、好奇"
    enable_local_fallback: bool = True   # 没网时自动切 Ollama
    tts_enabled: bool = False
    voice: str = "default"
    pet_skin: str = "02"

class ConfigManager:
    def __init__(self, path: str = "config.json"):
        self.path = path
        self.data = AppConfig()
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.data = AppConfig(**raw)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.data), f, ensure_ascii=False, indent=2)

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self.data, k, v)
        self.save()

