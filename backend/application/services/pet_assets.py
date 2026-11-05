"""桌宠资源目录:codex_pet / pixiv_pet 落在哪、由谁提供。

两条硬约束决定了这里不能再用「相对 CWD 的 ../Symbix_frontend/public」:

1. 打包后前端 dist 被编译进二进制,`tauri.localhost/codex_pet/...` 只能取到
   构建那一刻的快照。运行期新装的宠物(Codex 导入 / Petdex 安装 / pet-forge
   烘焙)永远不在里面 —— 所以这些目录必须由后端静态服务。
2. 安装目录可能不可写(Program Files),所以可写产物要落到用户数据目录,
   内置宠物在首次启动时从打包资源播种过去。

开发态(非 frozen)保持原样:直接用仓库里的 Symbix_frontend/public。
"""

import os
import shutil
import sys
from pathlib import Path

from application.state import BASE_DIR
from Symbix_sdk.app_paths import data_root, is_frozen

CODEX_PET = "codex_pet"
PIXIV_PET = "pixiv_pet"


def bundled_public_root() -> Path:
    """内置宠物所在目录(只读)。

    打包态:Tauri 的 bundle.resources 把仓库 public 映射到后端 exe 旁边
    (`backend/public`),而 BASE_DIR 是 `backend/_internal`,所以先看 ../public。
    开发态:退回仓库的 Symbix_frontend/public。
    """
    candidates = [
        Path(BASE_DIR).parent / "public",
        Path(BASE_DIR) / "public",
        Path(BASE_DIR).parent / "Symbix_frontend" / "public",
    ]
    for path in candidates:
        if path.is_dir():
            return path.resolve()
    return candidates[-1].resolve()


def pets_root() -> Path:
    """宠物根目录:PET_PUBLIC_DIR > 打包态 data/pets > 仓库 public。"""
    env = os.environ.get("PET_PUBLIC_DIR")
    if env:
        return Path(env).resolve()
    if is_frozen():
        custom = os.environ.get("SYMBIX_PETS_DIR")
        return (Path(custom) if custom else data_root() / "pets").resolve()
    return bundled_public_root()


def codex_pet_dir() -> Path:
    env = os.environ.get("PET_CODEX_DIR")
    return Path(env).resolve() if env else pets_root() / CODEX_PET


def pixiv_pet_dir() -> Path:
    env = os.environ.get("PET_PIXIV_DIR")
    return Path(env).resolve() if env else pets_root() / PIXIV_PET


def ensure_pet_dirs() -> None:
    """建目录;打包态首次启动把内置宠物播种到可写目录(只做一次)。

    播种靠一个 `.seeded` 标记,不是「目标缺失就补」:用户删掉的内置宠物
    不应该下次启动又冒回来。
    """
    root = pets_root()
    for target in (codex_pet_dir(), pixiv_pet_dir()):
        target.mkdir(parents=True, exist_ok=True)
    if not is_frozen():
        return
    source_root = bundled_public_root()
    if source_root == root:
        return
    marker = root / ".seeded"
    if marker.is_file():
        return
    seeded = 0
    for name in (CODEX_PET, PIXIV_PET):
        source = source_root / name
        if not source.is_dir():
            continue
        for folder in source.iterdir():
            target = root / name / folder.name
            if folder.is_dir() and not target.exists():
                try:
                    shutil.copytree(folder, target)
                    seeded += 1
                except OSError as e:  # noqa: BLE001
                    print(f"[pets] 播种内置宠物 {folder.name} 失败: {e}")
    try:
        marker.write_text(f"{seeded}\n", encoding="utf-8")
    except OSError:  # 写不了标记就下次再试,不值得让启动失败
        pass
    print(f"[pets] 宠物目录: {root}(播种 {seeded} 个内置宠物)")
