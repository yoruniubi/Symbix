from __future__ import annotations
import json
from Symbix_sdk.act_mode.child import CHILD_ROLES, run_child_agent, run_child_agents


def _task_context() -> str:
    """给子 Agent 的主链路上下文:主 Agent 在本会话里已经做过什么。

    子 Agent 是「只读、看不到主 Agent 对话历史」的,不告诉它前面做过什么,
    它就会去重复翻主 Agent 已经确认过的文件(白烧 token,还可能得出重复结论)。
    数据源同主链路的 [近期工具记录],压制得更短(见 CHILD_DIGEST_ROUNDS)。
    """
    from Symbix_sdk.checkpoint import get_current
    from application.services.round_digest import (
        CHILD_DIGEST_HEADER, CHILD_DIGEST_ROUNDS, build_recent_tool_digest,
    )

    session_id, _round_id = get_current()
    if not session_id:
        return ""
    try:
        return build_recent_tool_digest(
            session_id, header=CHILD_DIGEST_HEADER, rounds=CHILD_DIGEST_ROUNDS,
        )
    except Exception as e:
        print(f"[digest] 子 Agent 上下文构建失败,跳过: {e}")
        return ""


async def delegate_task(
    task: str = "",
    agent_role: str = "researcher",
    context: str = "",
    _on_event=None,
    _ctx: dict | None = None,
) -> str:
    """把一个子任务委派给只读子 Agent,返回其结论(JSON 字符串)。

    Args:
        task: 子任务描述(必填),要具体、可独立完成
        agent_role: 子 Agent 角色,可选 researcher/analyst/designer/tester/reviewer
        context: 可选,补充背景(已知信息、相关路径、约束等)
        _on_event: 内部注入,进度回调(非模型参数)
        _ctx: 内部注入,请求级模型参数(非模型参数)

    Returns:
        JSON 字符串:{"status", "agent_role", "tools_used", "rounds", "result"}
    """
    # 延迟导入,避免 SDK 模块加载时反向依赖 application 层
    from application.state import symbix_client, tool_registry

    ctx = _ctx or {}
    result = await run_child_agent(
        task,
        role=agent_role,
        context=context,
        task_context=_task_context(),
        llm_client=symbix_client,
        toolkit=tool_registry.native,
        override_api_key=ctx.get("api_key") or None,
        override_api_base=ctx.get("api_base") or None,
        override_model=ctx.get("model") or None,
        on_event=_on_event,
    )

    payload = {
        "status": "error" if result.get("error") else "ok",
        "agent_role": result.get("role_label") or result.get("role"),
        "tools_used": result.get("tools_used") or [],
        "rounds": result.get("rounds", 0),
        "result": result.get("content", ""),
    }
    return json.dumps(payload, ensure_ascii=False)


_ROLE_HINT = "/".join(CHILD_ROLES.keys())


def _summarize(results: list[dict], total: int, succeeded: int, failed: int,
              truncated: int, dropped: int = 0) -> str:
    """把批量结果拼成一段人类可读的编队摘要(置于 JSON 前,方便模型/前端快速浏览)。"""
    lines = [f"【子 Agent 编队结果】共 {total} 个,成功 {succeeded} 个,失败 {failed} 个"]
    if dropped:
        lines.append(f"(注:有 {dropped} 项子任务因缺少 task 描述被忽略)")
    if truncated:
        lines.append(f"(注:本次传入的子任务超过单次上限,已丢弃末尾 {truncated} 个)")
    for i, r in enumerate(results, 1):
        label = r.get("role_label") or r.get("role") or "?"
        tools = ",".join(r.get("tools_used") or []) or "未调用工具"
        flag = "失败" if r.get("error") else "完成"
        lines.append(f"{i}. [{label}] {flag}(工具: {tools})")
    return "\n".join(lines)


async def delegate_tasks(
    tasks: list | None = None,
    _on_event=None,
    _ctx: dict | None = None,
) -> str:
    """把多个「互不依赖」的子任务同时派给多个只读子 Agent 并发执行,汇总结论(JSON 字符串)。

    Args:
        tasks: 子任务列表,每项形如 {"task": "...", "agent_role": "...", "context": "..."}
        _on_event: 内部注入,进度回调(非模型参数)
        _ctx: 内部注入,请求级模型参数(非模型参数)

    Returns:
        JSON 字符串:{"status", "summary", "total", "succeeded", "failed", "results"}
    """
    # 延迟导入,避免 SDK 模块加载时反向依赖 application 层
    from application.state import symbix_client, tool_registry

    ctx = _ctx or {}
    batch = await run_child_agents(
        tasks,
        llm_client=symbix_client,
        toolkit=tool_registry.native,
        override_api_key=ctx.get("api_key") or None,
        override_api_base=ctx.get("api_base") or None,
        override_model=ctx.get("model") or None,
        task_context=_task_context(),
        on_event=_on_event,
    )

    results = batch.get("results") or []
    total = batch.get("total", 0)
    succeeded = batch.get("succeeded", 0)
    failed = batch.get("failed", 0)
    payload = {
        "status": "ok" if succeeded else "error",
        "summary": _summarize(results, total, succeeded, failed,
                              batch.get("truncated", 0), batch.get("dropped", 0))
                  if total else "[Error] 未提供有效的子任务(task 为空)",
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "dropped": batch.get("dropped", 0),
        "truncated": batch.get("truncated", 0),
        "results": [
            {
                "agent_role": r.get("role_label") or r.get("role"),
                "task": r.get("task", ""),
                "tools_used": r.get("tools_used") or [],
                "rounds": r.get("rounds", 0),
                "status": "error" if r.get("error") else "ok",
                "result": r.get("content", ""),
            }
            for r in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False)

AGENT_TOOLS_SCHEMAS = {
    "delegate_task": {
        # 子 Agent 只读 → read 通道 → SAFE 自动放行,不打断主流程
        "risk_channel": "read",
        "func": delegate_task,
        "description": (
            "把一个可独立完成的子任务委派给专门的只读子 Agent 去处理,拿到结论后再由你汇总。"
            "适合:在动手改动前,先摸清代码、分析根因、设计方案、设计测试或做代码审查。"
            f"可用角色 agent_role:{_ROLE_HINT}。"
            "注意:子 Agent 只能只读探索(读文件/搜代码/联网查),不能修改文件或执行命令;"
            "它返回的是分析与草案,真正落盘的改动必须由你自己用文件/终端工具完成(会走审批)。"
            "若后一个子任务需要依赖前一个的结论(串行),就连续多次调用本工具;"
            "若多个子任务互不依赖,改用 delegate_tasks 一次并发发出(更快,推荐)。"
            "简单、一步就能完成的事情不要委派——自己直接做更省时。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "交给子 Agent 的具体子任务,需自包含、可独立完成",
                },
                "agent_role": {
                    "type": "string",
                    "enum": list(CHILD_ROLES.keys()),
                    "description": (
                        "子 Agent 角色:researcher(定位代码)、analyst(分析问题)、"
                        "designer(设计方案)、tester(设计测试)、reviewer(代码审查)"
                    ),
                },
                "context": {
                    "type": "string",
                    "description": "可选:补充背景信息(已知线索、相关文件路径、约束条件)",
                },
            },
            "required": ["task"],
        },
    },
    "delegate_tasks": {
        # 同样只读 → read 通道 → SAFE 自动放行
        "risk_channel": "read",
        "func": delegate_tasks,
        "description": (
            "把多个「互不依赖」的子任务一次性同时派给多个只读子 Agent 并发执行(扇出/扇入),再汇总。"
            "当你需要同时了解多个模块、从多个角度分析、或一边查代码一边查资料时,"
            "用这个工具一次性发出去,比逐个调用 delegate_task 快得多。"
            "每一项可指定 agent_role:" + _ROLE_HINT + "。"
            "限制:一次最多 6 项,并发最多 4 路;子 Agent 只能只读探索(不能改文件/执行命令);"
            "单个子 Agent 失败不影响其它,失败项会在结果里标出。"
            "真正的写操作仍旧必须由你自己在主链路完成(会走审批)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "子任务列表(建议 2~4 项,最多 6 项),每项互不依赖",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "子任务描述,需自包含、可独立完成",
                            },
                            "agent_role": {
                                "type": "string",
                                "enum": list(CHILD_ROLES.keys()),
                                "description": "该子任务的角色(researcher/analyst/designer/tester/reviewer)",
                            },
                            "context": {
                                "type": "string",
                                "description": "可选:该子任务的补充背景",
                            },
                        },
                        "required": ["task"],
                    },
                },
            },
            "required": ["tasks"],
        },
    },
}
