from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
SDK = BACKEND / "Symbix_sdk"
MULTI_DIR = SDK / "stt" / "multi-platform"
MODEL_DIR = SDK / "stt" / "model"
DIST_ASSETS = BACKEND / "dist-assets"          # pack 产物输出目录(git 不收)
GGUF_NAME = "sense-voice-small-q4_k.gguf"
MANIFEST_NAME = "asset-manifest.json"

# <OS>-<arch> 名(与 resource_path.stt_platform_name 一致)→ zip 资产名 + 官方 bun/uv 资产名
PLATFORMS = {
    "Windows-x64": {
        "zip": "stt-native-windows-x64.zip",
        "bun": "bun-windows-x64.zip",
        "uv": ("uv-x86_64-pc-windows-msvc.zip", "uv.exe"),
    },
    "Linux-x64": {
        "zip": "stt-native-linux-x64.zip",
        "bun": "bun-linux-x64.zip",
        "uv": ("uv-x86_64-unknown-linux-gnu.tar.gz", "uv"),
    },
    "MacOS-arm64": {
        "zip": "stt-native-macos-arm64.zip",
        "bun": "bun-darwin-aarch64.zip",
        "uv": ("uv-aarch64-apple-darwin.tar.gz", "uv"),
    },
    "MacOS-x64": {
        "zip": "stt-native-macos-x64.zip",
        "bun": "bun-darwin-x64.zip",
        "uv": ("uv-x86_64-apple-darwin.tar.gz", "uv"),
    },
}
# bun/uv 版本:默认 pin(可复现构建;升级时改这两个常量,或 CI 传 --bun-version/--uv-version 覆盖)。
# 不用 latest:latest 不可复现,且上游改资产名会让 CI 莫名其妙红掉。
BUN_VERSION = "1.4.3"   # tag 形如 bun-v1.4.3
UV_VERSION = "0.13.5"   # tag 形如 0.13.5


def bun_base(version: str) -> str:
    """bun 下载前缀;version 传 latest 则取官方 latest(不推荐)。"""
    if version == "latest":
        return "https://github.com/oven-sh/bun/releases/latest/download/"
    return f"https://github.com/oven-sh/bun/releases/download/bun-v{version}/"


def uv_base(version: str) -> str:
    """uv 下载前缀;version 传 latest 则取官方 latest(不推荐)。"""
    if version == "latest":
        return "https://github.com/astral-sh/uv/releases/latest/download/"
    return f"https://github.com/astral-sh/uv/releases/download/{version}/"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_platform() -> str:
    """当前平台名(与 resource_path.stt_platform_name 相同规则,避免 import SDK 的重 __init__)。"""
    names = {"win32": "Windows", "linux": "Linux", "darwin": "MacOS"}
    archs = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}
    import platform
    os_name = names.get(sys.platform, "")
    arch = archs.get(platform.machine().lower(), "")
    if os_name and arch:
        return f"{os_name}-{arch}"
    raise SystemExit(f"[assets] 未知平台: {sys.platform} / {platform.machine()}")


def canon_platform(dir_name: str) -> str | None:
    """目录名 → 规范平台名(宽容解析,与 resource_path.stt_bin_dir 同规则)。

    容忍 CI 产出的 linux / macos 这类无架构后缀的名字(单架构时按该 OS 的
    主力架构归档:Windows/Linux→x64,MacOS→arm64);带后缀则原样识别。
    """
    parts = dir_name.lower().split("-")
    os_map = {"windows": "Windows", "linux": "Linux", "macos": "MacOS", "mac": "MacOS"}
    os_name = os_map.get(parts[0])
    if not os_name:
        return None
    arch = parts[1] if len(parts) > 1 else ("arm64" if os_name == "MacOS" else "x64")
    return f"{os_name}-{arch}"


def download(url: str, dest: Path) -> Path:
    """流式下载到 dest(临时文件 + 原子改名,失败不留半截文件)。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  下载 {url}")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as f:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1048576:6.1f} / {total / 1048576:.1f} MB", end="", flush=True)
    print()
    tmp.replace(dest)
    return dest


def load_manifest(base_url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{base_url}/{MANIFEST_NAME}") as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[assets] 警告: 拿不到 {MANIFEST_NAME}({e}),跳过 sha256 校验")
        return {}


# ---------------- pack:本机把 multi-platform 各平台打成 zip + 生成 manifest ----------------
def cmd_pack(args: argparse.Namespace) -> int:
    DIST_ASSETS.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    gguf = MODEL_DIR / GGUF_NAME
    if gguf.is_file():
        print(f"[pack] gguf: {gguf.name} {gguf.stat().st_size / 1048576:.1f} MB")
        manifest[GGUF_NAME] = sha256_of(gguf)
    else:
        print(f"[pack] 警告: 找不到 {gguf}(模型不打包,上传时单独加)")
    for src in sorted(MULTI_DIR.iterdir()) if MULTI_DIR.is_dir() else []:
        if not src.is_dir():
            continue
        plat = canon_platform(src.name)
        if plat is None:
            print(f"[pack] 跳过 {src.name}/(目录名认不出平台)")
            continue
        conf = PLATFORMS[plat]
        if not list(src.glob("sense-voice-stream*")):
            print(f"[pack] 跳过 {plat}(缺 sense-voice-stream —— 该平台 CI 未出 stream)")
            continue
        out = DIST_ASSETS / conf["zip"]
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(src.iterdir()):
                if f.is_file():
                    z.write(f, f.name)
        print(f"[pack] {plat}: {out.name} {out.stat().st_size / 1048576:.1f} MB "
              f"({len(list(src.iterdir()))} 文件)")
        manifest[conf["zip"]] = sha256_of(out)
    out_m = DIST_ASSETS / MANIFEST_NAME
    out_m.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[pack] manifest -> {out_m}")
    print("[pack] 上传(手动,一次性):")
    print(f"  gh release create assets-v1 --title \"runtime assets\" --notes \"STT/model/bun/uv assets\" || true")
    print(f"  gh release upload assets-v1 dist-assets/* --clobber")
    return 0


# ---------------- fetch:下载资产补齐源码树 ----------------
def extract_zip_member(zpath: Path, member: str, dest: Path, strip_dirs: int) -> None:
    """从 zip 里取一个文件(strip_dirs = 去掉的前导目录层数)。"""
    with zipfile.ZipFile(zpath) as z:
        target = next(n for n in z.namelist() if n.split("/")[-1] == member)
        z.extract(target, dest.parent)
        got = dest.parent / target
        got.replace(dest) if strip_dirs == 0 else shutil.move(str(got), str(dest))


def fetch_runtime(url_base: str, name: str, member: str, dest: Path, suffix: str) -> None:
    """下载官方 bun/uv 包并取出可执行文件。suffix: ".zip" 或 ".tar.gz"。"""
    if dest.exists():
        print(f"[fetch] 已存在,跳过: {dest.name}")
        return
    z = download(url_base + name, Path(tempfile.gettempdir()) / name)
    if suffix == ".zip":
        with zipfile.ZipFile(z) as zf:
            target = next(n for n in zf.namelist() if n.split("/")[-1] == member)
            with zf.open(target) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    else:
        with tarfile.open(z) as tf:
            target = next(n for n in tf.getnames() if n.split("/")[-1] == member)
            with tf.extractfile(target) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    os.chmod(dest, 0o755)
    z.unlink()
    print(f"[fetch] -> {dest} ({dest.stat().st_size / 1048576:.1f} MB)")


def cmd_fetch(args: argparse.Namespace) -> int:
    plat = detect_platform()
    conf = PLATFORMS[plat]
    base_url = args.base_url or f"https://github.com/{args.repo}/releases/download/{args.tag}"
    print(f"[fetch] 平台 {plat} / 资产源 {base_url}")
    manifest = load_manifest(base_url)

    # 1. gguf 模型(平台无关)
    gguf = MODEL_DIR / GGUF_NAME
    if gguf.is_file():
        print(f"[fetch] gguf 已存在,跳过")
    else:
        f = download(f"{base_url}/{GGUF_NAME}", gguf)
        want = manifest.get(GGUF_NAME)
        if want and sha256_of(f) != want:
            f.unlink()
            raise SystemExit("[fetch] gguf sha256 不符,已删除(资产或下载损坏)")
        print(f"[fetch] -> {f} ({f.stat().st_size / 1048576:.1f} MB)")

    # 2. stt 原生栈 zip → multi-platform/<平台>/(spec 从这里按平台搬运)
    target_dir = MULTI_DIR / plat
    if any(target_dir.glob("sense-voice-stream*")):
        print(f"[fetch] stt 原生栈已存在,跳过: {target_dir}")
    else:
        zname = conf["zip"]
        z = download(f"{base_url}/{zname}", Path(tempfile.gettempdir()) / zname)
        want = manifest.get(zname)
        if want and sha256_of(z) != want:
            z.unlink()
            raise SystemExit(f"[fetch] {zname} sha256 不符,已删除")
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if n.endswith("/"):
                    continue
                (target_dir / Path(n).name).write_bytes(zf.read(n))
                if not sys.platform.startswith("win"):
                    os.chmod(target_dir / Path(n).name, 0o755)
        z.unlink()
        print(f"[fetch] -> {target_dir} ({len(list(target_dir.iterdir()))} 文件)")
    return 0


def cmd_fetch_runtimes(args: argparse.Namespace) -> int:
    """bun/uv:默认取 pin 版本(可复现),--bun-version/--uv-version latest 可改为追官方最新。"""
    plat = detect_platform()
    conf = PLATFORMS[plat]
    bun_name, uv_name = conf["bun"], conf["uv"][0]
    bun_member = "bun.exe" if plat.startswith("Windows") else "bun"
    bun_dest = SDK / bun_member
    uv_member = "uv.exe" if plat.startswith("Windows") else "uv"
    uv_dest = SDK / uv_member
    if not bun_dest.exists():
        fetch_runtime(bun_base(args.bun_version), bun_name, bun_member, bun_dest, ".zip")
    if not uv_dest.exists():
        fetch_runtime(uv_base(args.uv_version), uv_name, uv_member, uv_dest,
                      ".zip" if uv_name.endswith(".zip") else ".tar.gz")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Symbix 发版资产工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pack", help="本机:把 multi-platform 打成 zip + 生成 manifest")

    f = sub.add_parser("fetch", help="CI/新人:下载资产补齐源码树")
    f.add_argument("--repo", default="", help="资产所在仓库 OWNER/REPO(默认取 GITHUB_REPOSITORY)")
    f.add_argument("--tag", default="assets-v1", help="资产 Release 的 tag")
    f.add_argument("--base-url", default="", help="直接给资产 base URL(本地测试用 file:///...)")
    f.add_argument("--skip-runtimes", action="store_true", help="跳过 bun/uv(只取 gguf/stt)")
    f.add_argument("--bun-version", default=BUN_VERSION,
                   help=f"bun 版本(默认 pin {BUN_VERSION};传 latest 取官方最新)")
    f.add_argument("--uv-version", default=UV_VERSION,
                   help=f"uv 版本(默认 pin {UV_VERSION};传 latest 取官方最新)")
    f.set_defaults(func=None)

    args = ap.parse_args()
    if args.cmd == "pack":
        return cmd_pack(args)
    # fetch:先 gguf/stt,再 bun/uv(可分别跳过)
    repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")
    if not args.base_url and not repo:
        raise SystemExit("[fetch] 需要 --repo OWNER/REPO 或 --base-url")
    rc = cmd_fetch(args)
    if not args.skip_runtimes:
        rc = rc or cmd_fetch_runtimes(args)
    return rc


if __name__ == "__main__":
    sys.exit(main())
