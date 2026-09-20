"""Skill / Native Tools 管理路由。"""
import os
from fastapi import APIRouter, HTTPException

from application.schemas import CreateSkillRequest, InstallSkillCliRequest, InstallSkillGithubRequest
from application.state import BASE_DIR, skill_registry, tool_registry

router = APIRouter(tags=["skills"])


@router.get("/native/tools")
async def list_native_tools():
    """列出所有内置 native 工具（不含 skill 工具）"""
    tools = tool_registry.get_native_only_tools()
    return {"count": len(tools), "tools": tools}


@router.get("/skills/tools")
async def list_skill_tools():
    """列出所有 skill 注册的工具（skill__ 前缀）"""
    tools = tool_registry.get_skill_tools()
    return {"count": len(tools), "tools": tools}


@router.get("/skills")
async def get_skills():
    """获取所有已安装的 skill 列表"""
    skills = skill_registry.list()
    return {
        "skills": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
                "trigger_keywords": s.trigger_keywords,
            }
            for s in skills
        ]
    }


@router.post("/skills/install/github")
async def install_skill_github(req: InstallSkillGithubRequest):
    """从 GitHub 安装 skill"""
    from Symbix_sdk.skill.installer import install_skill_from_github

    if not (req.repo_url or "").strip():
        raise HTTPException(status_code=400, detail="repo_url 不能为空")
    result = install_skill_from_github(
        repo_url=req.repo_url,
        skill_name=req.skill_name,
        target_dir=skill_registry.skills_dir,
        branch=req.branch or "",
        overwrite=req.overwrite,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("error") or "安装 skill 失败"
        )

    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "path": result.get("path"),
        "source": result.get("source"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@router.post("/skills/install/cli")
async def install_skill_cli(req: InstallSkillCliRequest):
    """通过官方 skills CLI 直接安装(对标: npx skills add <name>,支持包名/仓库短名/URL)"""
    from Symbix_sdk.skill.installer import SkillCliError, install_skill_via_cli

    if not (req.package or "").strip():
        raise HTTPException(status_code=400, detail="package 不能为空")
    try:
        result = install_skill_via_cli(
            package=req.package,
            skill_name=req.skill_name,
            target_dir=skill_registry.skills_dir,
            overwrite=req.overwrite,
        )
    except SkillCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "安装 skill 失败")

    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "path": result.get("path"),
        "source": result.get("source"),
        "run_type": result.get("run_type"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@router.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """删除已安装 skill 并热刷新。"""
    from Symbix_sdk.skill.installer import uninstall_skill

    result = uninstall_skill(skill_name, skill_registry.skills_dir)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "删除失败")
    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@router.post("/skills/create")
async def create_skill(req: CreateSkillRequest):
    """创建 skill 骨架目录"""
    # skill-creator 目录取名含连字符（不是合法 Python 包名），且 init_skill.py 位于其中。
    # 因此走 importlib 按文件路径加载，避免 import 语句拼包名时被逐字识别。
    import importlib.util

    init_path = os.path.join(
        BASE_DIR,
        "Symbix_sdk",
        "skill",
        "installed_skills",
        "skill-creator",
        "scripts",
        "init_skill.py",
    )
    if not os.path.exists(init_path):
        raise HTTPException(
            status_code=500, detail=f"init_skill.py 不存在: {init_path}"
        )
    spec = importlib.util.spec_from_file_location("symbix_init_skill", init_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    create_skill_skeleton = mod.create_skill_skeleton

    result = create_skill_skeleton(
        skill_name=req.skill_name,
        description=req.description,
        display_name=req.display_name,
        purpose=req.purpose,
        instructions=req.instructions,
        target_dir=skill_registry.skills_dir,
        overwrite=req.overwrite,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("error") or "创建 skill 失败"
        )

    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "path": result.get("path"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@router.post("/skills/reload")
async def reload_skills():
    """重新扫描并加载 skills，并刷新已注册的 skill 工具"""
    skill_registry.scan()
    tool_registry.refresh_skills()
    return {"status": "ok", "count": len(skill_registry.list())}


@router.get("/skills/match")
async def match_skills(user_input: str):
    """根据用户输入匹配相关 skill"""
    matched = skill_registry.find_by_trigger(user_input)
    return {
        "matched": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
            }
            for s in matched
        ]
    }


@router.get("/debug/skills-path")
def debug_skills_path():
    return {
        "skills_dir": skill_registry.skills_dir,
        "absolute_path": os.path.abspath(skill_registry.skills_dir),
        "cwd": os.getcwd(),
        "exists": os.path.exists(skill_registry.skills_dir),
        "loaded_skills": (
            skill_registry.list_skills()
            if hasattr(skill_registry, "list_skills")
            else list(skill_registry._skills.keys())
        ),
    }
