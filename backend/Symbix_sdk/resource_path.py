import os
import platform
import sys
from pathlib import Path

# ---- 相对资源根的固定布局(与 spec 的搬运目标一一对应,两边不能各改各的)----
_STT_BIN_DIR = "Symbix_sdk/stt/bin"                # 运行期位置:spec 把当前平台那份拷到这里
_STT_MULTI_DIR = "Symbix_sdk/stt/multi-platform"   # 来源:SenseVoice.cpp 多平台编译产物
_STT_MODEL_DIR = "Symbix_sdk/stt/model"            # gguf 模型,平台无关

# sys.platform → (目录名规范写法, 允许的目录名前缀[小写])
# multi-platform/ 下的目录名形如 Windows-x64 / linux / macos,解析时忽略大小写、
# 架构后缀可有可无(见 stt_bin_dir)。
_OS_INFO = {
    "win32": ("Windows", ("windows",)),
    "linux": ("Linux", ("linux",)),
    "darwin": ("MacOS", ("macos", "mac")),
}
# platform.machine()(小写)→ 目录名架构段
_ARCH_NAMES = {
    "amd64": "x64", "x86_64": "x64",
    "arm64": "arm64", "aarch64": "arm64",
}


def resource_root() -> Path:
    """资源根目录:SYMBIX_RESOURCE_DIR > PyInstaller _MEIPASS > 源码树 backend/。"""
    env = os.environ.get("SYMBIX_RESOURCE_DIR")
    if env:
        return Path(env)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def resource(rel: str) -> Path:
    """按相对路径取资源,根目录规则见 resource_root()。"""
    return resource_root() / rel


def sdk_binary(rel_noext: str) -> Path:
    """SDK 内置可执行文件的路径,按平台自动补 .exe 后缀。

    rel_noext 不带扩展名,如 "Symbix_sdk/bun" / "Symbix_sdk/uv"。
    Windows 命中 Symbix_sdk/bun.exe,macOS/Linux 命中 Symbix_sdk/bun ——
    调用方不再硬编码 .exe(以前写死 bun.exe,macOS/Linux 永远找不到,
    还会被误判为「没捆绑」甚至拿到 Windows PE 直接 exec 崩)。
    是否真的存在由调用方自行判断(降级路径需要拿 None 而不是抛错)。
    """
    return resource(rel_noext + (".exe" if sys.platform == "win32" else ""))


def stt_platform_name() -> str:
    """当前平台的 multi-platform 规范目录名,如 Windows-x64 / MacOS-arm64。

    未知平台或未知架构返回空串(调用方回退到旧 stt/bin)。
    """
    info = _OS_INFO.get(sys.platform)
    arch = _ARCH_NAMES.get(platform.machine().lower())
    if not info or not arch:
        return ""
    return f"{info[0]}-{arch}"


def stt_bin_dir() -> Path:
    """STT 原生栈目录(exe 与同目录的 DLL/dylib 必须待在一起)。

    优先 multi-platform/ 下匹配当前平台的目录(见 stt_platform_name 的宽容规则:
    忽略大小写;带架构后缀的目录必须匹配当前架构,且优先于不带后缀的目录 ——
    这样将来同时存在 macos(arm64)与 MacOS-x64 时,两边都能拿对);找不到再回退旧的
    stt/bin。打包后 multi-platform 不会进发行包,自然命中 stt/bin。
    """
    info = _OS_INFO.get(sys.platform)
    multi = resource(_STT_MULTI_DIR)
    if info and multi.is_dir():
        prefixes, arch = info[1], _ARCH_NAMES.get(platform.machine().lower())
        found = []  # (优先级, 目录): 0 = 架构后缀匹配, 1 = 无后缀(单架构)
        for d in sorted(multi.iterdir()):
            if not d.is_dir():
                continue
            parts = d.name.lower().split("-")
            if parts[0] not in prefixes:
                continue
            if len(parts) == 1:
                found.append((1, d))
            elif arch and parts[1] == arch:
                found.append((0, d))
        if found:
            return min(found, key=lambda t: t[0])[1]
    return resource(_STT_BIN_DIR)


def stt_model_dir() -> Path:
    """STT gguf 模型目录(平台无关)。"""
    return resource(_STT_MODEL_DIR)
