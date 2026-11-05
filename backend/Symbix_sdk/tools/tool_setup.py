from __future__ import annotations
from Symbix_sdk.tools.builtin.file_tools import FILE_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.doc_tools import DOC_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.pet_tools import PET_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.skill_tools import SKILL_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.terminal_tools import TERMINAL_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.web_tools import  WEB_TOOLS_SCHEMAS 
from Symbix_sdk.tools.builtin.interaction_tools import INTERACTION_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.agent_tools import AGENT_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.job_tools import JOB_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.memory_tools import MEMORY_TOOLS_SCHEMAS
from Symbix_sdk.tools.builtin.extension_tools import EXTENSION_TOOLS_SCHEMAS
ALL_TOOL_SCHEMAS = {}
ALL_TOOL_SCHEMAS.update(FILE_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(DOC_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(PET_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(SKILL_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(TERMINAL_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(WEB_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(INTERACTION_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(AGENT_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(JOB_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(MEMORY_TOOLS_SCHEMAS)
ALL_TOOL_SCHEMAS.update(EXTENSION_TOOLS_SCHEMAS)

def setup_builtin_tools(toolkit) -> None:
    """将定义在所有子模块中的工具注册到给定的 NativeToolkit 实例。

    调用时机:
        NativeToolkit.__init__ 后调用一次；
        SkillRegistry 重置后也可重新调用。

    Args:
        toolkit: NativeToolkit 实例
    """
    import sys
    import os

    # 默认 skill 安装目录(供 create_skill 回退使用):属于用户数据,走 app_paths
    from Symbix_sdk.app_paths import data_path
    _DEFAULT_SKILLS_DIR = data_path("Symbix_sdk/skill/installed_skills")

    for name, spec in ALL_TOOL_SCHEMAS.items():
        func = spec["func"]
        desc = spec["description"]
        params = spec["parameters"]

        # 特殊处理: create_skill 需要绑定 _skill_registry、默认路径、重注册回调
        if name == "create_skill":
            _raw_func = func

            def _make_bound_create_skill(raw_func):
                def _bound(**kwargs):
                    return raw_func(
                        _skill_registry=toolkit._skill_registry,
                        _default_skills_dir=_DEFAULT_SKILLS_DIR,
                        _on_skill_created=toolkit.register_skill_tools,
                        **kwargs,
                    )
                return _bound

            toolkit.register_tool(
                name=name,
                func=_make_bound_create_skill(func),
                description=desc,
                parameters=params,
            )
        # 特殊处理: skill 安装/卸载工具需要绑定注册表 + 默认目录 + 重注册回调
        elif name in ("install_skill", "remove_skill"):

            def _make_bound_skill_action(raw_func):
                # 包装函数必须是 async:外层据 iscoroutinefunction 判定是否走 execute_async,
                # 同步包装会把协程对象直接当结果返回
                async def _bound(**kwargs):
                    return await raw_func(
                        _skill_registry=toolkit._skill_registry,
                        _skills_dir=_DEFAULT_SKILLS_DIR,
                        _on_skills_changed=toolkit.register_skill_tools,
                        **kwargs,
                    )

                return _bound

            toolkit.register_tool(
                name=name,
                func=_make_bound_skill_action(func),
                description=desc,
                parameters=params,
            )
        # 特殊处理: MCP 安装/删除/查询工具需要绑定应用侧的配置与连接管理器
        elif name in ("install_mcp_server", "remove_mcp_server", "list_mcp_servers"):

            def _make_bound_mcp_action(raw_func):
                async def _bound(**kwargs):
                    return await raw_func(_mcp_binding=toolkit._mcp_binding, **kwargs)

                return _bound

            toolkit.register_tool(
                name=name,
                func=_make_bound_mcp_action(func),
                description=desc,
                parameters=params,
            )
        else:
            toolkit.register_tool(
                name=name,
                func=func,
                description=desc,
                parameters=params,
            )