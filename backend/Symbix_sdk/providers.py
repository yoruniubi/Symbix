from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import os
import json
import shutil


@dataclass
class ProviderConfig:
    name: str
    model: str          # litellm 格式，如 "anthropic/claude-sonnet-4-6" 或 "ollama/qwen2.5"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    # ── 能力位（显式覆盖；None=由 provider_class 默认推断）
    # 这套位以 pi 的 capability flag 为参照：显式开关 + 不支持时优雅降级，
    # 以便“死命测”不会因模型不支持 stdin /vision / reasoning / cache 而 422/500。
    supports_streaming: Optional[bool] = None
    supports_tools: Optional[bool] = None
    supports_reasoning: Optional[bool] = None       # reasoning_effort / thinking 参数
    supports_vision: Optional[bool] = None
    supports_prompt_cache: Optional[bool] = None     # 是否发 cache_control / prompt_cache_key
    api_kind: Optional[str] = None    # "openai_compat" | "anthropic" | "gemini" | None(自动推断)


# 基于模型前缀的内置能力默认表。用户可在 providers.json 覆盖。
# 这里只对主要 provider 给默认值；未知前缀按 openai_compat 的保守默认走。
_PROVEDER_CAPABILITY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "openai": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=None,
        supports_vision=None, supports_prompt_cache=True, api_kind="openai_compat",
    ),
    "anthropic": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=True,
        supports_vision=True, supports_prompt_cache=True, api_kind="anthropic",
    ),
    "gemini": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=True,
        supports_vision=True, supports_prompt_cache=False, api_kind="gemini",
    ),
    # deepseek-tools 走 OpenAI 兼容协议；reasoner 支持 reasoning。
    "deepseek": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=None,
        supports_vision=False, supports_prompt_cache=True, api_kind="openai_compat",
    ),
    "moonshot": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=False,
        supports_vision=False, supports_prompt_cache=True, api_kind="openai_compat",
    ),
    "xai": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=True,
        supports_vision=True, supports_prompt_cache=True, api_kind="openai_compat",
    ),
    "qwen": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=True,
        supports_vision=True, supports_prompt_cache=False, api_kind="openai_compat",
    ),
    "zhipu": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=False,
        supports_vision=True, supports_prompt_cache=False, api_kind="openai_compat",
    ),
    "groq": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=False,
        supports_vision=False, supports_prompt_cache=False, api_kind="openai_compat",
    ),
    "openrouter": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=None,
        supports_vision=None, supports_prompt_cache=True, api_kind="openai_compat",
    ),
    "ollama": dict(
        supports_streaming=True, supports_tools=True, supports_reasoning=False,
        supports_vision=None, supports_prompt_cache=False, api_kind="openai_compat",
    ),
}

# 安全默认：未知 provider 按 OpenAI 兼容 + 不假设任何高级能力。
_SAFE_DEFAULT = dict(
    supports_streaming=True, supports_tools=False, supports_reasoning=False,
    supports_vision=False, supports_prompt_cache=False, api_kind="openai_compat",
)


def resolve_capabilities(model: str, provider_cfg: Optional[ProviderConfig] = None) -> Dict[str, Any]:
    """返回当前 provider 的能力位。用户显式覆盖优先于内置默认。"""
    prefix = model.split("/", 1)[0].lower() if "/" in model else "openai"
    base = dict(_PROVEDER_CAPABILITY_DEFAULTS.get(prefix, _SAFE_DEFAULT))
    if provider_cfg is not None:
        for k in ("supports_streaming", "supports_tools", "supports_reasoning",
                  "supports_vision", "supports_prompt_cache", "api_kind"):
            v = getattr(provider_cfg, k, None)
            if v is not None:
                base[k] = v
    return base


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
                    "supports_streaming": p.supports_streaming,
                    "supports_tools": p.supports_tools,
                    "supports_reasoning": p.supports_reasoning,
                    "supports_vision": p.supports_vision,
                    "supports_prompt_cache": p.supports_prompt_cache,
                    "api_kind": p.api_kind,
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