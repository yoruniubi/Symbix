from __future__ import annotations
import json
import os
import threading

class DanmakuConfig:
    """弹幕功能配置(默认值)。"""

    def __init__(self) -> None:
        self.enabled: bool = True            # 弹幕总开关
        self.idle_enabled: bool = True       # 空闲漫游弹幕开关
        self.greeting_enabled: bool = True   # 时段问候弹幕开关
        self.idle_interval_s: int = 600      # 空闲弹幕最小间隔(秒)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "idle_enabled": self.idle_enabled,
            "greeting_enabled": self.greeting_enabled,
            "idle_interval_s": self.idle_interval_s,
        }

    def apply(self, patch: dict) -> None:
        """部分更新,只接受自己字段。"""
        allowed = set(self.to_dict().keys())
        for k, v in (patch or {}).items():
            if k in allowed and v is not None:
                setattr(self, k, v)


class DanmakuConfigManager:
    """弹幕配置读写,持久化到 config/danmaku_config.json。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.cfg = DanmakuConfig()
        self._lock = threading.Lock()
        self._load()

    # ---- io ----
    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.cfg.apply(raw if isinstance(raw, dict) else {})
        except Exception as e:
            print(f"[danmaku] 配置读取失败(用默认值): {e}")

    def save(self) -> None:
        with self._lock:
            data = self.cfg.to_dict()
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def apply_patch(self, patch: dict) -> None:
        self.cfg.apply(patch)
        self.save()

    def reset(self) -> None:
        self.cfg = DanmakuConfig()
        self.save()