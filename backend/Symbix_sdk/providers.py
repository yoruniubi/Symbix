from dataclasses import dataclass
from typing import Optional
import os
import json
import shutil


@dataclass
class ProviderConfig:
    name: str
    model: str          # litellm 格式，如 "anthropic/claude-sonnet-4-6" 或 "ollama/qwen2.5"
    api_key: Optional[str] = None
    api_base: Optional[str] = None


class ProviderRegistry:
    """管理多个 provider 配置，支持切换和持久化"""

    def __init__(self, config_path: str = "providers.json"):
        self.config_path = config_path
        self.providers: dict[str, ProviderConfig] = {}
        self.active: Optional[str] = None
        self._load()

    def _load(self):
        # 首次启动：如果真实配置文件不存在，从 .example 模板复制
        if not os.path.exists(self.config_path):
            example_path = self.config_path + ".example"
            if os.path.exists(example_path):
                shutil.copy2(example_path, self.config_path)

        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for name, cfg in data.get("providers", {}).items():
                    self.providers[name] = ProviderConfig(name=name, **cfg)
                self.active = data.get("active")

    def save(self):
        data = {
            "active": self.active,
            "providers": {
                name: {
                    "model": p.model,
                    "api_key": p.api_key,
                    "api_base": p.api_base,
                }
                for name, p in self.providers.items()
            },
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, name: str, model: str, api_key: str = None, api_base: str = None):
        self.providers[name] = ProviderConfig(name, model, api_key, api_base)
        if self.active is None:
            self.active = name
        self.save()

    def set_active(self, name: str):
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not found")
        self.active = name
        self.save()

    def get_active(self) -> ProviderConfig:
        if self.active is None:
            raise RuntimeError("No active provider set")
        return self.providers[self.active]