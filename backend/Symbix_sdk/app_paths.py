"""用户数据目录:开发态 = 仓库 backend/,打包态 = <安装目录>/data。

为什么需要这层:

- 打包后程序目录可能落在只读位置(如 C:\\Program Files),运行期写配置/数据库会
  直接失败;
- 用户数据(API key、数据库、上传与 Agent 生成的文件、桌宠皮肤、自装 skill)原本
  混在 backend/_internal/ 里,只是靠打包器「只删它认识的文件」这个副作用才活过
  升级,很脆;
- 源码运行时又必须保持原样(仓库里的 Symbix_sdk/... 是 git 跟踪的开发数据)。

约定:

- 只读资源(程序、内置模板、内置 skill 源)仍从 bundle 读,不动;
- 一切运行期可写的东西都走 ``data_path(...)``;
- 开发态返回的路径与改动前**完全一致**,不影响本地开发和测试;
- 打包态首次启动把旧位置的数据一次性**复制**(不删源)到 <安装目录>/data/,
  之后所有读写都走新位置。
"""

import hashlib
import os
import shutil
import sys
from pathlib import Path

# Symbix_sdk/ 的上一级 = backend/ 或 PyInstaller 的 _internal/
_BASE_DIR = Path(__file__).resolve().parents[1]

# 开发态相对 backend/ 的目录 → 打包态相对 data/ 的目录
_LAYOUT = {
    "Symbix_sdk/config": "config",
    "Symbix_sdk/memory": "memory",
    "Symbix_sdk/skill/installed_skills": "skills",
    "uploads": "uploads",
}

# 打包态 data/ 下需要预先建好的目录(桌宠目录由 pet_assets 自己建)
DATA_SUBDIRS = tuple(_LAYOUT.values()) + ("pets",)

MIGRATION_MARKER = ".migrated_v1"
SKILL_SIGNATURE = ".bundled_signature"
_PROBE_NAME = ".write_probe"

_data_root_cache: Path | None = None


def is_frozen() -> bool:
    """PyInstaller 打包态。"""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """程序资源根(只读)。打包态是 _internal/,开发态是 backend/。"""
    return _BASE_DIR


def install_root() -> Path:
    """打包态 = 安装目录,开发态 = 仓库根。

    后端 exe 在 <安装目录>/backend/SymbixBackend.exe,故上两级即安装目录。
    """
    if not is_frozen():
        return _BASE_DIR.parent
    exe = Path(sys.executable).resolve()
    if exe.parent.name.lower() == "backend":
        return exe.parent.parent
    return _BASE_DIR.parent


def _probe_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / _PROBE_NAME
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def fallback_data_root() -> Path:
    """安装目录不可写时的退路(Program Files / 只读盘安装)。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / "Symbix" if base else Path.home() / ".symbix"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Symbix"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "Symbix"


def data_root() -> Path:
    """可写数据根。SYMBIX_DATA_DIR > <安装目录>/data > 仓库 backend/。

    结果会缓存:启动时探测一次可写性,失败自动退到用户目录,后续不再变。
    """
    global _data_root_cache
    if _data_root_cache is not None:
        return _data_root_cache

    env = os.environ.get("SYMBIX_DATA_DIR")
    if env:
        root = Path(env).expanduser().resolve()
    elif is_frozen():
        root = install_root() / "data"
    else:
        root = _BASE_DIR

    if not _probe_writable(root):
        fallback = fallback_data_root()
        print(f"[data] {root} 不可写,改用 {fallback}")
        root = fallback
        _probe_writable(root)

    _data_root_cache = root
    return root


def data_path(dev_rel: str, *parts: str) -> str:
    """数据目录下某个文件的绝对路径。

    Args:
        dev_rel: 开发态相对 backend/ 的目录,必须是 _LAYOUT 的键
                 (如 "Symbix_sdk/config")
        *parts: 该目录下的子路径

    Returns:
        绝对路径字符串(目录不一定已存在)
    """
    sub = _LAYOUT[dev_rel] if is_frozen() else dev_rel
    path = data_root().joinpath(*sub.split("/"))
    if parts:
        path = path.joinpath(*parts)
    return str(path)


def ensure_data_dirs() -> None:
    """建好 data/ 下的固定目录(失败不阻断启动,后续写入时还会再试)。"""
    root = data_root()
    for sub in DATA_SUBDIRS:
        try:
            root.joinpath(sub).mkdir(parents=True, exist_ok=True)
        except OSError as e:  # noqa: BLE001
            print(f"[data] 建目录失败 {root / sub}: {e}")


def _copy_missing(src: Path, dst: Path) -> int:
    """递归复制,目标已存在的一律跳过(只增不覆盖)。返回复制文件数。"""
    copied = 0
    if src.is_file():
        if dst.exists():
            return 0
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return 1
        except OSError as e:  # noqa: BLE001
            print(f"[data] 复制失败 {src} -> {dst}: {e}")
            return 0
    try:
        dst.mkdir(parents=True, exist_ok=True)
    except OSError as e:  # noqa: BLE001
        print(f"[data] 建目录失败 {dst}: {e}")
        return 0
    for item in src.iterdir():
        if item.name == "__pycache__":
            continue
        copied += _copy_missing(item, dst / item.name)
    return copied


def migrate_legacy_data() -> None:
    """打包态首次启动:把旧位置(_internal/...)的数据复制到 data/。

    只复制不删源;目标已存在的文件一律不覆盖;-wal/-shm 与主库一起搬,避免丢
    最近事务。成功与否都写标记,保证只跑一次(用户手动清空 data/ 才会再跑)。
    """
    if not is_frozen():
        return
    root = data_root()
    first_run = not (root / MIGRATION_MARKER).is_file()

    copied = 0
    for dev_rel, sub in _LAYOUT.items():
        src = _BASE_DIR.joinpath(*dev_rel.split("/"))
        if not src.is_dir():
            continue
        # 已迁过的机器仍要回头补 config:早期构建有几份 json(voice/risk_trust/
        # exec_whitelist/danmaku)没走 data_path,一直写在 _internal/ 里,升级就丢。
        # 这里按「目标缺失才拷」幂等补齐,不覆盖用户在 data/ 里改过的值;
        # config 只有几十个小文件,每次启动扫一遍的开销可忽略。
        if not first_run and sub != "config":
            continue
        copied += _copy_missing(src, root / sub)

    # 早期构建把桌宠写进过 %LOCALAPPDATA%\Symbix\pets,一并收编
    legacy_pets = fallback_data_root() / "pets"
    target_pets = root / "pets"
    try:
        if legacy_pets.is_dir() and legacy_pets.resolve() != target_pets.resolve():
            copied += _copy_missing(legacy_pets, target_pets)
    except OSError:
        pass

    try:
        if first_run:
            (root / MIGRATION_MARKER).write_text(
                f"copied={copied}\n", encoding="utf-8"
            )
    except OSError as e:  # 写不了标记下次再试,不值得让启动失败
        print(f"[data] 迁移标记写入失败: {e}")
    if copied:
        print(f"[data] 旧数据已迁至 {root}({copied} 个文件,源目录保留)")


def _skills_signature(root: Path) -> str:
    """内置 skill 目录的内容签名(路径 + 内容哈希),用来判断是否需要刷新。

    用内容哈希而不是修改时间:打包/解包会改写 mtime,只看时间会每次启动都全量
    重拷;只看大小则漏掉「改了但长度不变」的脚本改动。整个内置 skill 只有几百 KB。
    """
    digest = hashlib.sha1()
    for path in sorted(root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(hashlib.sha1(data).digest())
    return digest.hexdigest()


def sync_bundled_skills() -> None:
    """打包态把内置 skill 铺到 data/skills,内容变化(升级)时刷新。

    内置 skill 是程序逻辑(pet-forge 的 bake/pack 脚本、skill-creator 的骨架生成
    器),必须跟着版本更新,所以这里按内容签名整目录替换;用户自建的 skill 不在
    内置清单里,不会被碰到。开发态直接用仓库里的目录,跳过。
    """
    if not is_frozen():
        return
    bundled = _BASE_DIR / "Symbix_sdk" / "skill" / "installed_skills"
    if not bundled.is_dir():
        return
    target = data_root() / "skills"
    signature = _skills_signature(bundled)
    marker = target / SKILL_SIGNATURE
    if marker.is_file():
        try:
            if marker.read_text(encoding="utf-8").strip() == signature:
                return
        except OSError:
            pass

    refreshed = 0
    for skill in sorted(bundled.iterdir()):
        if not skill.is_dir():
            continue
        dst = target / skill.name
        try:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill, dst)
            refreshed += 1
        except OSError as e:  # noqa: BLE001
            print(f"[skills] 同步内置 skill {skill.name} 失败: {e}")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(signature + "\n", encoding="utf-8")
    except OSError as e:  # noqa: BLE001
        print(f"[skills] 签名写入失败: {e}")
    print(f"[skills] 内置 skill 已同步到 {target}({refreshed} 个)")


def bootstrap_data_dirs() -> None:
    """启动最早调用:建目录 → 迁移旧数据 → 同步内置 skill。

    必须在 application.state 被导入之前执行 —— 那里在模块级就把 db/config 的
    路径定下来了,marker / 迁移都要赶在第一个连接打开之前完成。
    """
    ensure_data_dirs()
    migrate_legacy_data()
    sync_bundled_skills()
