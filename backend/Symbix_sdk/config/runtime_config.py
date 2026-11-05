"""运行期可调参数:长任务的轮次上限与累积工具结果 token 预算。

为什么单独一份而不是环境变量:打包版用户没有终端,设置页需要能改;而这两个
数字直接决定「多步任务能不能跑完」和「一次失控能烧多少 token」,是最需要用户
自己拿主意的两个旋钮。

三档预设:
- standard : 40 轮 / 300k  —— 保守,适合日常问答;
- relaxed  : 80 轮 / 1M    —— 默认。300k 是旧版「长任务腰斩」的真正元凶,放宽
                              到 1M 基本等于「长任务跑得完」,同时还有止损点;
- unlimited: 不限制         —— 只在明确知道自己要跑很久时选。仍受两道兜底保护:
                              同一调用重复拦截(MAX_SAME_CALL_EXECUTIONS)、
                              连续被拦就收尾;但**没有** token 止损,出错时只能点停止。

环境变量(SYMBIX_MAX_TOOL_ROUNDS / SYMBIX_MAX_CUM_TOOL_TOKENS)优先级最高,
便于排障与 CI;0 表示不限制。
"""

from __future__ import annotations

import json
import os
import threading

from Symbix_sdk.app_paths import data_path

# 档位 → (轮次上限, 累积工具 token 预算);0 表示不限制
PRESETS: dict[str, dict[str, int]] = {
    "standard": {"max_tool_rounds": 40, "max_cum_tool_tokens": 300_000},
    "relaxed": {"max_tool_rounds": 80, "max_cum_tool_tokens": 1_000_000},
    "unlimited": {"max_tool_rounds": 0, "max_cum_tool_tokens": 0},
}

DEFAULT_MODE = "relaxed"
MODES = tuple(PRESETS.keys())


def _env_int(name: str) -> int | None:
    """读环境变量里的非负整数;缺失或非法返回 None(用预设值)。"""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        print(f"[runtime_config] 环境变量 {name}={raw!r} 不是整数,已忽略")
        return None


class RuntimeConfig:
    """长任务档位。改档位立即生效,下一个请求就用新值。"""

    def __init__(self) -> None:
        self.mode: str = DEFAULT_MODE

    def preset(self) -> dict[str, int]:
        return dict(PRESETS.get(self.mode, PRESETS[DEFAULT_MODE]))

    def max_tool_rounds(self) -> int:
        """单次请求里最多跑几轮「模型 → 工具 → 模型」(0 = 不限制)。"""
        env = _env_int("SYMBIX_MAX_TOOL_ROUNDS")
        return env if env is not None else self.preset()["max_tool_rounds"]

    def max_cum_tool_tokens(self) -> int:
        """累积工具结果 token 预算,超了就收尾(0 = 不限制)。"""
        env = _env_int("SYMBIX_MAX_CUM_TOOL_TOKENS")
        return env if env is not None else self.preset()["max_cum_tool_tokens"]

    def to_dict(self) -> dict:
        return {"mode": self.mode, **self.preset()}

    def apply(self, patch: dict) -> None:
        """只接受合法档位名,其他字段一律忽略。"""
        mode = (patch or {}).get("mode")
        if isinstance(mode, str) and mode in PRESETS:
            self.mode = mode


class RuntimeConfigManager:
    """读写 config/runtime_config.json。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.cfg = RuntimeConfig()
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.cfg.apply(raw if isinstance(raw, dict) else {})
        except Exception as e:  # noqa: BLE001
            print(f"[runtime_config] 读取失败(用默认档位): {e}")

    def save(self) -> None:
        with self._lock:
            data = {"mode": self.cfg.mode}
            _d = os.path.dirname(self.path)
            if _d:
                os.makedirs(_d, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def apply_patch(self, patch: dict) -> None:
        self.cfg.apply(patch)
        self.save()

    def reset(self) -> None:
        self.cfg = RuntimeConfig()
        self.save()


runtime_config = RuntimeConfigManager(
    data_path("Symbix_sdk/config", "runtime_config.json")
)
