from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, Optional

CHILD_ALLOWED_TOOLS = frozenset({
    "list_files",
    "read_file",
    "search_files",
    "search_file_with_name",
    "parse_file",
    "doc_to_markdown",
    "search_online",
    "fetch_webpage",
})

# 角色 → (中文标签, 角色专属指令)
CHILD_ROLES: dict[str, tuple[str, str]] = {
    "researcher": (
        "代码检索员",
        "任务是定位相关代码/文件并梳理关系。产出:相关文件清单(带路径)、关键函数/类位置、"
        "调用或依赖关系、以及一句话说明每个位置的用途。",
    ),
    "analyst": (
        "问题分析员",
        "任务是分析某个模块或问题的成因与影响面。产出:根因判断、支撑证据(文件/代码片段)、"
        "影响范围、以及可能的其他解释。",
    ),
    "designer": (
        "方案设计员",
        "任务是为某个改动设计实现方案。产出:改动点清单(精确到文件)、每处的实现思路、"
        "关键代码草案(以文本形式给出完整片段,不要落盘),以及需要注意的兼容性/风险点。",
    ),
    "tester": (
        "测试设计员",
        "任务是为某个功能设计测试与验证方案。产出:测试用例清单(含正常/边界/异常)、"
        "每个用例的步骤与预期结果、可执行的验证命令草案(文本形式),以及建议的回归范围。",
    ),
    "reviewer": (
        "代码审查员",
        "任务是审查代码的正确性与安全性。产出:问题清单(按严重度排序)、每条的代码证据与位置、"
        "修复建议、以及你确认没有问题的方面。关注空指针/越界/竞态/注入/权限/资源泄漏。",
    ),
}

DEFAULT_ROLE = "researcher"

# 子 Agent 单次工具结果截断长度(防止子上下文爆炸)
_MAX_TOOL_RESULT_CHARS = 8000
# 回传给主 Agent 的结论截断长度(保护主上下文)
_MAX_CONTENT_CHARS = 6000
# 并行扇出护栏:单次批量委派的子 Agent 数量上限与并发度
_MAX_BATCH = 6
_DEFAULT_CONCURRENCY = 4
# 批量委派时单个子 Agent 的默认超时与结论截断(比单个委派更紧,避免多路叠加过久/过大)
_DEFAULT_CHILD_TIMEOUT = 120.0
_BATCH_CHILD_CONTENT_CHARS = 3000

_BASE_PROMPT = """你是一个被主 Agent 委派的子 Agent,专门负责「{role_label}」子任务。

你只能使用只读工具(读文件、搜代码、解析文档、联网查资料)来收集证据。
你不能修改任何文件、不能执行命令、也不能向用户提问——需要落盘的改动由主 Agent 负责。

工作规则:
1. 先用只读工具核实事实,再下结论;绝不凭空猜测代码内容。
2. 结论要具体可核查:给出文件路径、函数/类名、关键代码片段等定位信息。
3. 若信息不足或相互矛盾,明确写出「不确定」与缺失项,不要编造。
4. 直接输出你的最佳分析结果,不要寒暄、不要复述任务。
5. 输出语言与用户请求保持一致(默认中文)。

{role_instruction}
"""


def resolve_role(role: Optional[str]) -> tuple[str, str, str]:
    """把角色名规范化为 (role_key, role_label, role_instruction)。未知角色回退默认。"""
    key = (role or "").strip().lower() or DEFAULT_ROLE
    if key not in CHILD_ROLES:
        key = DEFAULT_ROLE
    label, instruction = CHILD_ROLES[key]
    return key, label, instruction


def build_child_system_prompt(role: str) -> str:
    """按角色拼出子 Agent 的 system prompt。"""
    _, label, instruction = resolve_role(role)
    return _BASE_PROMPT.format(role_label=label, role_instruction=instruction)


def build_child_tools(toolkit, allowed: frozenset | None = None) -> list[dict]:
    """从 toolkit 中筛出只读白名单工具的 OpenAI schema,并排除 delegate_task 防递归。"""
    allow = allowed or CHILD_ALLOWED_TOOLS
    out: list[dict] = []
    for spec in toolkit.get_openai_tools():
        fn = spec.get("function") or {}
        name = fn.get("name")
        if name in allow and name not in ("delegate_task", "delegate_tasks"):
            out.append(spec)
    return out


async def run_child_agent(
    task: str,
    *,
    role: str = DEFAULT_ROLE,
    context: str = "",
    llm_client,
    toolkit,
    override_api_key: str | None = None,
    override_api_base: str | None = None,
    override_model: str | None = None,
    max_rounds: int = 6,
    overall_timeout: float = 180.0,
    max_content_chars: int = _MAX_CONTENT_CHARS,
    on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """执行一次子 Agent 委派,返回结论。

    Args:
        task: 交给子 Agent 的子任务描述(必填)
        role: 角色键(researcher/analyst/designer/tester/reviewer),未知则回退 researcher
        context: 附加背景(主 Agent 可把已知信息/相关路径喂进来)
        llm_client: SymbixClient 实例(非流式 chat 内核)
        toolkit: NativeToolkit 实例(提供只读工具)
        override_api_key / override_api_base / override_model: 请求级模型参数(可选)
        max_rounds: 子 Agent 工具循环上限
        overall_timeout: 整个子任务的超时(秒)
        max_content_chars: 回传结论的截断长度
        on_event: 可选 async 回调,用于向主链路推送进度事件

    Returns:
        {"content": str, "role": str, "role_label": str,
         "tools_used": list[str], "rounds": int, "error": str | None}
    """
    role_key, role_label, _ = resolve_role(role)
    task = (task or "").strip()
    if not task:
        return {
            "content": "[Error] 子任务描述(task)为空",
            "role": role_key, "role_label": role_label,
            "tools_used": [], "rounds": 0, "error": "empty task",
        }

    system_prompt = build_child_system_prompt(role_key)
    tools = build_child_tools(toolkit)
    allowed_names = {t["function"]["name"] for t in tools}

    user_msg = task
    if context and context.strip():
        user_msg = f"{task}\n\n[已知背景]\n{context.strip()}"

    async def _emit(ev: dict) -> None:
        if on_event is None:
            return
        try:
            await on_event(ev)
        except Exception:
            pass

    async def _run() -> dict:
        from Symbix_sdk.providers import resolve_capabilities

        provider = llm_client.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        api_key_val = override_api_key or provider.api_key
        caps = resolve_capabilities(raw_model, provider)

        messages = llm_client._build_messages(
            [], user_msg, registry=None, tools=tools, system_prompt=system_prompt,
        )

        tools_used: list[str] = []
        last_content = ""
        rounds = 0
        loop_error: str | None = None

        while rounds < max_rounds:
            rounds += 1
            resp = await llm_client._chat_raw(
                messages, tools, raw_model, raw_base, api_key_val, caps
            )
            if resp.get("content"):
                last_content = resp["content"]
            # 上游模型调用失败(如 503 / 鉴权失败):立即停止,并如实标记为失败,
            # 否则会把「没拿到任何结论」当成成功报给主 Agent。
            if resp.get("error"):
                loop_error = str(resp["error"])
                break
            tool_calls = resp.get("tool_calls")
            if not tool_calls:
                break

            round_results: list[dict] = []
            for tc in tool_calls:
                name = tc.get("name") or ""
                args = tc.get("arguments", "{}")
                if name in allowed_names:
                    await _emit({"phase": "tool_start", "agent_role": role_key,
                                 "round": rounds, "tool": name})
                    out = await toolkit.execute_tool_async(name, args)
                    tools_used.append(name)
                    await _emit({"phase": "tool_end", "agent_role": role_key,
                                 "round": rounds, "tool": name})
                else:
                    out = (
                        f"[Error] 子 Agent 不允许调用工具 '{name}';"
                        f"可用只读工具: {sorted(allowed_names)}"
                    )
                if not isinstance(out, str):
                    out = str(out)
                if len(out) > _MAX_TOOL_RESULT_CHARS:
                    out = out[:_MAX_TOOL_RESULT_CHARS] + "\n...[结果已截断]"
                round_results.append({
                    "tool_call_id": tc.get("id") or name,
                    "role": "tool",
                    "name": name,
                    "content": out,
                    "arguments": args,
                })
            llm_client._build_tool_result_messages(messages, round_results)

        content = (last_content or "").strip()
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n\n...[结论已截断]"
        if loop_error:
            content = (content + "\n\n" if content else "") + f"[Error] 上游模型调用失败: {loop_error}"
            return {
                "content": content,
                "role": role_key, "role_label": role_label,
                "tools_used": tools_used, "rounds": rounds, "error": loop_error,
            }
        if not content:
            # 没产出任何结论:对调用方而言这是失败,不能静默算成功
            return {
                "content": "[子 Agent 未产出结论(可能达到轮次上限、模型无文本输出或被限流)。]",
                "role": role_key, "role_label": role_label,
                "tools_used": tools_used, "rounds": rounds, "error": "no content",
            }

        return {
            "content": content,
            "role": role_key,
            "role_label": role_label,
            "tools_used": tools_used,
            "rounds": rounds,
            "error": None,
        }

    try:
        return await asyncio.wait_for(_run(), timeout=overall_timeout)
    except asyncio.TimeoutError:
        return {
            "content": f"[Error] 子 Agent「{role_label}」执行超时({overall_timeout:.0f}s)",
            "role": role_key, "role_label": role_label,
            "tools_used": [], "rounds": 0, "error": "timeout",
        }
    except Exception as e:  # 兜底:子 Agent 失败不应拖垮主链路
        return {
            "content": f"[Error] 子 Agent「{role_label}」执行失败: {e}",
            "role": role_key, "role_label": role_label,
            "tools_used": [], "rounds": 0, "error": str(e),
        }


def _normalize_batch_tasks(tasks) -> tuple[list[dict], int]:
    """把批量委派入参规范成 (子任务列表, 被丢弃的无效项数)。

    兼容三种写法:纯字符串列表、单条 dict、dict 列表。
    缺少 task 或 task 为空的项会被丢弃(并在返回里报数,避免静默少派任务)。
    """
    if tasks is None:
        return [], 0
    if isinstance(tasks, dict):
        tasks = [tasks]
    elif isinstance(tasks, str):
        tasks = [{"task": tasks}]
    if not isinstance(tasks, (list, tuple)):
        return [], 1
    out: list[dict] = []
    dropped = 0
    for item in tasks:
        if isinstance(item, str):
            spec = {"task": item}
        elif isinstance(item, dict):
            spec = item
        else:
            dropped += 1
            continue
        task_text = str(spec.get("task") or "").strip()
        if not task_text:
            dropped += 1  # 空任务不发子 Agent
            continue
        out.append({
            "task": task_text,
            "agent_role": str(spec.get("agent_role") or DEFAULT_ROLE).strip() or DEFAULT_ROLE,
            "context": str(spec.get("context") or "").strip(),
        })
    return out, dropped


async def run_child_agents(
    tasks,
    *,
    llm_client,
    toolkit,
    override_api_key: str | None = None,
    override_api_base: str | None = None,
    override_model: str | None = None,
    max_concurrency: int = _DEFAULT_CONCURRENCY,
    max_rounds: int = 6,
    child_timeout: float = _DEFAULT_CHILD_TIMEOUT,
    max_content_chars: int = _BATCH_CHILD_CONTENT_CHARS,
    on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """并发扇出多个子 Agent(扇出/扇入),单个失败不影响其它。

    与 run_child_agent 的区别:这里一次把多个「互不依赖」的子任务同时发出去,
    用信号量限制并发度,再汇总所有结论。事件里额外带 slot / total / done,
    便于主链路把「几路并行、完成几路」展示给用户。

    Args:
        tasks: 子任务列表,每项可为字符串或 {task, agent_role, context}
        max_concurrency: 同时运行的子 Agent 数上限
        child_timeout: 每个子 Agent 的超时(秒)
        max_content_chars: 每个子 Agent 结论的截断长度(批量会压得更短)
        on_event: 可选 async 进度回调

    Returns:
        {"results": list[dict], "total": int, "succeeded": int,
         "failed": int, "dropped": int, "truncated": int, "error": str | None}
    """
    normalized, dropped = _normalize_batch_tasks(tasks)
    total = len(normalized)
    if total == 0:
        return {"results": [], "total": 0, "succeeded": 0, "failed": 0,
                "dropped": dropped, "truncated": 0, "error": "empty tasks"}

    # 超量直接截断(护栏:防止模型一次派几十个子 Agent 把 token 烧光)
    truncated = max(0, total - _MAX_BATCH)
    if truncated:
        normalized = normalized[:_MAX_BATCH]
        total = len(normalized)

    done = 0
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _emit(ev: dict) -> None:
        if on_event is None:
            return
        try:
            await on_event(ev)
        except Exception:
            pass

    async def _one(idx: int, spec: dict) -> dict:
        nonlocal done
        role_key = resolve_role(spec["agent_role"])[0]

        async def _child_event(ev: dict) -> None:
            async with lock:
                snapshot = done
            await _emit({**ev, "slot": idx, "total": total, "done": snapshot})

        async with sem:  # 限流:最多 max_concurrency 路同时跑
            await _emit({"phase": "child_start", "slot": idx, "total": total,
                         "done": done, "agent_role": role_key})
            result = await run_child_agent(
                spec["task"],
                role=spec["agent_role"],
                context=spec["context"],
                llm_client=llm_client,
                toolkit=toolkit,
                override_api_key=override_api_key,
                override_api_base=override_api_base,
                override_model=override_model,
                max_rounds=max_rounds,
                overall_timeout=child_timeout,
                max_content_chars=max_content_chars,
                on_event=_child_event,
            )
        async with lock:
            done += 1
            snapshot = done
        await _emit({"phase": "child_end", "slot": idx, "total": total,
                     "done": snapshot, "agent_role": role_key})
        return result

    raw = await asyncio.gather(
        *[_one(i, spec) for i, spec in enumerate(normalized)],
        return_exceptions=True,
    )

    results: list[dict] = []
    failed = 0
    for idx, item in enumerate(raw):
        if isinstance(item, BaseException):  # 理论上不会发生(run_child_agent 自带兜底)
            failed += 1
            results.append({
                "role": resolve_role(normalized[idx]["agent_role"])[0],
                "role_label": resolve_role(normalized[idx]["agent_role"])[1],
                "task": normalized[idx]["task"],
                "content": f"[Error] 子 Agent 执行异常: {item}",
                "tools_used": [], "rounds": 0, "error": str(item),
            })
            continue
        if item.get("error"):
            failed += 1
        item = {**item, "task": normalized[idx]["task"]}
        results.append(item)

    return {
        "results": results,
        "total": total,
        "succeeded": total - failed,
        "failed": failed,
        "dropped": dropped,
        "truncated": truncated,
        "error": "all failed" if failed == total else None,
    }
