"""从 GitHub 仓库安装 Skill（对标 Claude Code: npx skills add <repo> --skill <name>）"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional
from urllib.parse import urlparse


def _normalize_repo_url(repo_url: str) -> str:
    url = (repo_url or "").strip()
    if not url:
        raise ValueError("仓库 URL 不能为空")

    # 允许 github.com/owner/repo 这种无协议写法
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")

    # 去掉 .git 末尾多余斜杠
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def _guess_skill_name_from_url(repo_url: str) -> str:
    path = urlparse(repo_url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "skill"
    return parts[-1]


def _find_skill_dir(root: str, skill_name: str) -> Optional[str]:
    """在仓库中查找包含 SKILL.md 的 skill 目录。"""
    target = skill_name.strip().lower().replace("_", "-")
    candidates: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过 .git
        dirnames[:] = [d for d in dirnames if d != ".git"]
        if "SKILL.md" not in filenames and "skill.md" not in filenames:
            continue
        base = os.path.basename(dirpath)
        rel = os.path.relpath(dirpath, root)
        candidates.append(dirpath)
        if base.lower().replace("_", "-") == target:
            return dirpath
        # 也允许 skills/frontend-design 这类路径末段匹配
        if rel.replace("\\", "/").lower().endswith("/" + target) or rel.replace("\\", "/").lower() == target:
            return dirpath

    # 若只有一个 SKILL.md，且用户没指定明确名称冲突，可回退
    if len(candidates) == 1 and (not skill_name or skill_name == _guess_skill_name_from_url(root)):
        return candidates[0]

    # 再尝试：根目录本身就是 skill
    if os.path.exists(os.path.join(root, "SKILL.md")) or os.path.exists(os.path.join(root, "skill.md")):
        if not skill_name or os.path.basename(root).lower().replace("_", "-") == target:
            return root

    return None


def install_skill_from_github(
    repo_url: str,
    skill_name: str,
    target_dir: str,
    branch: str = "",
    overwrite: bool = False,
) -> dict:
    """
    从 GitHub 安装 skill。

    等价体验：
      npx skills add https://github.com/anthropics/skills --skill frontend-design
    """
    repo_url = _normalize_repo_url(repo_url)
    skill_name = (skill_name or "").strip()
    if not skill_name:
        skill_name = _guess_skill_name_from_url(repo_url)

    # 目标名规范化
    dest_name = re.sub(r"[^a-z0-9\-]+", "-", skill_name.lower()).strip("-")
    if not dest_name:
        raise ValueError("无效的 skill 名称")

    dest_path = os.path.join(target_dir, dest_name)
    if os.path.exists(dest_path):
        if not overwrite:
            return {
                "ok": False,
                "error": f"Skill '{dest_name}' 已存在，如需覆盖请设置 overwrite=true",
            }
        shutil.rmtree(dest_path)

    os.makedirs(target_dir, exist_ok=True)

    tmp_root = tempfile.mkdtemp(prefix="symbix-skill-")
    clone_dir = os.path.join(tmp_root, "repo")
    try:
        # 优先 shallow clone
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url if repo_url.endswith(".git") else repo_url + ".git", clone_dir]

        # 某些环境 git 接受无 .git 的 https URL 也可以
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            return {"ok": False, "error": "未检测到 git，请先安装 Git"}

        if result.returncode != 0:
            # 再试一次不带 .git
            cmd2 = ["git", "clone", "--depth", "1"]
            if branch:
                cmd2 += ["--branch", branch]
            cmd2 += [repo_url, clone_dir]
            result = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "clone failed").strip()
                return {"ok": False, "error": f"克隆仓库失败: {err[:500]}"}

        found = _find_skill_dir(clone_dir, skill_name)
        if not found:
            # 列出可用 skill 帮助用户
            available = []
            for dirpath, dirnames, filenames in os.walk(clone_dir):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                if "SKILL.md" in filenames or "skill.md" in filenames:
                    available.append(os.path.relpath(dirpath, clone_dir).replace("\\", "/"))
            hint = f"可用 skill: {', '.join(available[:20])}" if available else "仓库中未找到 SKILL.md"
            return {
                "ok": False,
                "error": f"未找到 skill '{skill_name}'。{hint}",
                "available": available,
            }

        shutil.copytree(found, dest_path)
        # 确保有 SKILL.md 标准名
        lower = os.path.join(dest_path, "skill.md")
        upper = os.path.join(dest_path, "SKILL.md")
        if os.path.exists(lower) and not os.path.exists(upper):
            os.rename(lower, upper)

        return {
            "ok": True,
            "skill_name": dest_name,
            "path": dest_path,
            "source": repo_url,
            "message": f"Skill '{dest_name}' 已从 {repo_url} 安装",
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def uninstall_skill(skill_name: str, target_dir: str) -> dict:
    name = (skill_name or "").strip()
    if not name:
        return {"ok": False, "error": "skill_name 不能为空"}
    # 安全：只允许目录名
    if "/" in name or "\\" in name or name in (".", ".."):
        return {"ok": False, "error": "非法 skill 名称"}
    path = os.path.join(target_dir, name)
    if not os.path.isdir(path):
        return {"ok": False, "error": f"Skill '{name}' 不存在"}
    shutil.rmtree(path)
    return {"ok": True, "skill_name": name, "message": f"Skill '{name}' 已删除"}
