from __future__ import annotations
import json
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
    # 安全:只允许目录名
    if "/" in name or "\\" in name or name in (".", ".."):
        return {"ok": False, "error": "非法 skill 名称"}
    path = os.path.join(target_dir, name)
    if not os.path.isdir(path):
        return {"ok": False, "error": f"Skill '{name}' 不存在"}
    shutil.rmtree(path)
    return {"ok": True, "skill_name": name, "message": f"Skill '{name}' 已删除"}


def _resolve_cli_executable(*names: str) -> Optional[str]:
    """在 PATH 中查找可执行文件,支持 .cmd/.exe 变体。"""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


class SkillCliError(RuntimeError):
    """skills CLI 不可用/无法启动时抛出(HTTP 503)。"""


def install_skill_via_cli(
    package: str,
    target_dir: str,
    skill_name: str = "",
    overwrite: bool = False,
) -> dict:
    """通过官方 skills CLI 安装(对标 `npx skills add <name>`)。

    支持仓库短名(vercel-labs/agent-skills)、包名(notion)、GitHub URL 等;本机无 npx 时自动降级 SDK 内置 bun.exe(`bun x skills add`)。

    :param package: add 的目标(仓库短名 / 包名 / URL)
    :param target_dir: 安装目标目录
    :param skill_name: 可选,仓库内指定 skill 名
    :param overwrite: 是否覆盖
    """
    import subprocess as sp
    from Symbix_sdk.resource_path import resource

    package = (package or "").strip()
    if not package:
        raise ValueError("package 不能为空")
    skill_name = (skill_name or "").strip()

    # 运行器:优先 npx,未装则降级 SDK 内置 bun(平台后缀由 sdk_binary 处理)
    npx = _resolve_cli_executable("npx", "npx.cmd", "npx.exe")
    bun = None
    if not npx:
        try:
            from Symbix_sdk.resource_path import sdk_binary
            bun_path = sdk_binary("Symbix_sdk/bun")
            if os.path.exists(str(bun_path)):
                bun = str(bun_path)
        except Exception:
            bun = None

    if npx:
        base = ["npx", "-y", "skills", "add", package, "--json", "-y", "--copy"]
        if skill_name:
            base += ["--skill", skill_name]
    elif bun:
        base = [bun, "x", "skills", "add", package, "--json", "-y", "--copy"]
        if skill_name:
            base += ["--skill", skill_name]
    else:
        return {"ok": False, "error": "未检测到 npx 且无 SDK 内置 bun,无法运行 skills CLI", "run_type": None}

    use_shell = bool(npx)  # npx 是 .cmd 脚本需 shell;bun.exe 是原生二进制走参数列表
    tmp_root = tempfile.mkdtemp(prefix="symbix-skill-cli-")
    try:
        try:
            if use_shell:
                cmd_line = base[0] + " " + " ".join(f'"{a}"' if " " in a else a for a in base[1:])
                result = sp.run(cmd_line, cwd=tmp_root, capture_output=True, shell=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            else:
                result = sp.run(base, cwd=tmp_root, capture_output=True, shell=False, text=True, encoding="utf-8", errors="replace", timeout=600)
        except sp.TimeoutExpired:
            return {"ok": False, "error": "skills add 超时(>600s)", "run_type": "npx" if npx else "bun"}
        except FileNotFoundError:
            return {"ok": False, "error": "npx 或 bun.exe 启动失败", "run_type": "npx" if npx else "bun"}

        stdout = result.stdout or ""
        # skills CLI 会输出 npm 警告行,JSON 在后面,取最后一个 [ .. ]
        start = stdout.find("[")
        end = stdout.rfind("]")
        installed = []
        if start >= 0 and end > start:
            try:
                data = json.loads(stdout[start:end + 1])
                installed = [d for d in data if d.get("status") == "installed"]
            except json.JSONDecodeError:
                pass

        if result.returncode != 0 or not installed:
            detail = (result.stderr or result.stdout or "").strip()
            return {
                "ok": False,
                "error": f"skills add 失败(rc={result.returncode}): {detail[-300:]}",
                "run_type": "npx" if npx else "bun",
            }

        # 安装成功后把产物从临时 cwd 拷到目标目录
        # CLI 输出里给出所有实际安装路径(可能一次 install 装多个 skill)
        copied: list[dict] = []
        for item in installed:
            nm = item.get("name", "")
            src = item.get("path", "")
            if not nm or not src or not os.path.isdir(src):
                # 个别条目缺路径不致命,跳过它继续装其余的
                continue
            dest_path = os.path.join(target_dir, nm)
            if os.path.exists(dest_path):
                if not overwrite:
                    # 已存在时不覆盖,且不再继续?不——仅跳过该 skill,不整体失败
                    copied.append({"name": nm, "path": dest_path, "skipped": "exists"})
                    continue
                shutil.rmtree(dest_path)
            os.makedirs(target_dir, exist_ok=True)
            shutil.copytree(src, dest_path)
            copied.append({"name": nm, "path": dest_path, "skipped": False})

        if not copied:
            return {"ok": False, "error": f"CLI 无可用安装产物: {installed}", "run_type": "npx" if npx else "bun"}

        installed_names = [c["name"] for c in copied]
        msg = (
            f"{len(installed_names)} 个 Skill 已通过 {'npx' if npx else 'bun'} skills CLI 安装:"
            f" {', '.join(installed_names)}"
        )
        return {
            "ok": True,
            "skill_name": installed_names[0],
            "skill_names": installed_names,
            "installed": copied,
            "path": copied[0]["path"],
            "source": package,
            "run_type": "npx" if npx else "bun",
            "message": msg,
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
