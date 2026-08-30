import os
import sys
from pathlib import Path

# 相对资源根的固定布局(与源码目录保持一致,方便打包脚本整目录搬运)
_STT_BIN_DIR = "Symbix_sdk/stt/bin"
_STT_MODEL_DIR = "Symbix_sdk/stt/model"


def resource_root() -> Path:
    """资源根目录。优先级:环境变量 > PyInstaller _MEIPASS > 源码 backend/。"""
    env_dir = os.environ.get("SYMBIX_RESOURCE_DIR")
    if env_dir:
        return Path(env_dir)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)

    # __file__ = backend/Symbix_sdk/resource_path.py → 上两级 = backend/
    return Path(__file__).resolve().parent.parent


def resource(rel: str) -> Path:
    """拼出资源绝对路径(不保证存在,调用方自行判断)。"""
    return resource_root() / rel


def stt_bin_dir() -> Path:
    return resource(_STT_BIN_DIR)


def stt_model_dir() -> Path:
    return resource(_STT_MODEL_DIR)
