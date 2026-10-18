from __future__ import annotations
import asyncio
import json as _json
import time
from datetime import datetime

from Symbix_sdk.time_context import current_time_line

# 定时任务「整次模型调用」的重试次数与退避基数(秒)。
# 内层 _stream_with_retry 已经会重试单次调用,这里再叠一层「整次调用重试」;
# 上层还有 wait_for 硬上限托底,所以次数不宜多(否则最坏耗时成倍增长)。
JOB_MODEL_ATTEMPTS = 2
JOB_RETRY_BASE_DELAY = 15.0

# 单次模型调用硬上限 / 单次调用(含内层重试)的预算 / 一次任务给模型的总预算。
# 上游「接了连接不发数据」时,不能白等满默认 300s 读超时
# (旧行为最坏 3 次整次 × 3 次内层 × 300s ≈ 45 分钟,用户只看到面板卡死)。
# 整轮上限很必要:一轮任务最多 25 个工具轮,只限单次的话总时长仍会失控。
JOB_READ_TIMEOUT = 90.0
JOB_CALL_TIMEOUT = 150.0
JOB_CALL_BUDGET = 240.0
JOB_RUN_BUDGET = 600.0

# 一次性任务失败后的整轮补偿重试:提醒晚到 1 分钟好过丢掉
JOB_ONE_SHOT_RUN_ATTEMPTS = 2
JOB_COMPENSATE_DELAY = 60.0

# 无人值守必须屏蔽的两个交互工具:它们会挂起等用户回答,定时任务没人回答。
# 只在 job 链路拦,正常对话不受影响。
UNATTENDED_BLOCKED_TOOLS = ("ask_clarifying_question", "propose_plan")

# 这条追加在固定 system 规则**最后**(system_tail),因为 client 里那段固定规则
# 含「多步任务先报计划、等用户点头」,不压过去的话定时任务反而会先问用户。
UNATTENDED_SYSTEM_TAIL = (
    "\n\n## 无人值守(定时任务,优先于上面所有冲突的规则)\n"
    "- 没有人会回答你:**不要调用 `ask_clarifying_question`、不要调用 `propose_plan`、"
    "不要要求用户确认或选择**,也不要输出「等你点头我再做」之类的待确认计划。\n"
    "- 需要取舍的地方,自己选最合理的一种直接做完,在回复里一句话说明你选了什么。\n"
    "- 不要把任务本身当成话题讨论(比如改频率、改配置、查上一次报错),"
    "除非任务指令明确要求这么做;你的职责是把指令执行掉。\n"
    "- 最终回复用 1-2 句人话给结论:做了什么 / 有什么需要用户知道。"
)


def _raise_if_upstream_failed(response: dict) -> None:
    """上游报错且零输出时抛错,让 job 走 except 分支被标记为 error。

    非流式链路把上游错误只放进 error 字段、content 留空;
    不检查就会把网关故障(坏 key/坏 base/超时)记成「任务成功」。
    模型正常调工具时 content 为空但 tool_calls 有值,不算失败。
    """
    if response.get("error") and not (response.get("content") or "").strip() and not response.get("tool_calls"):
        raise RuntimeError(f"模型调用失败: {response['error']}")


class JobRunner:
    """持有 storage + storage 元 + 各业务单例的引用，执行一次 job。"""

    def __init__(self, storage, scheduler, memory, tool_registry, skill_registry,
                 symbix_client, provider_registry, checkpoint_recorder, pet_action) -> None:
        self.storage = storage
        self.scheduler = scheduler
        self.memory = memory
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
        self.symbix_client = symbix_client
        self.provider_registry = provider_registry
        self.checkpoint_recorder = checkpoint_recorder
        self.pet_action = pet_action

    # scheduler 通过这两个方法回调
    def get_meta(self, job_id: str):
        return self.storage.get_meta(job_id)

    async def execute(self, job: dict) -> str:
        """执行一次 job,返回 "ok" / "error"。一次性任务失败补偿一次,跑完标记 completed。"""
        one_shot = job.get("trigger_type") == "date"
        attempts = JOB_ONE_SHOT_RUN_ATTEMPTS if one_shot else 1
        status = "error"
        for i in range(1, attempts + 1):
            last = i == attempts
            # 首跑失败先不通知:补偿成功就不该给用户发失败提示
            status = await self._execute_once(job, report=last)
            if status == "ok" or last:
                break
            print(f"[job] 「{job.get('name', '')}」首跑失败,{JOB_COMPENSATE_DELAY:.0f}s 后补偿重试一次")
            await asyncio.sleep(JOB_COMPENSATE_DELAY)
        if one_shot:
            try:
                self.storage.set_completed(job["id"], True)
            except Exception as e:
                print(f"[job] 标记 completed 失败: {e}")
        return status

    async def _execute_once(self, job: dict, report: bool = True) -> str:
        """真正跑一轮 job。report=False 表示后面还会补偿重试,先不发失败通知。"""
        from Symbix_sdk.checkpoint import set_current as _ctx_set_current
        from Symbix_sdk.checkpoint import get_recorder
        from Symbix_sdk.tools.risk_classifier import classify_tool_risk, ToolRiskLevel

        job_id = job["id"]
        sid = job.get("session_id")
        run_time = datetime.now()

        # 无 session → 自动建一个固定「定时任务」session（每个 job 长期复用，攒上下文）
        if not sid:
            sid = f"schedule__{job_id}"
            job["session_id"] = sid
            self.storage.upsert_meta(job)

        output_snippet = ""
        output_full = ""          # 错误分支也要用:早出错时它还没被赋值
        ckpt_round_id = ""
        try:
            self.memory.add(sid, "user", job["prompt"])
            history = self.memory.get_compressed_history(sid, recent_limit=20)

            provider = self.provider_registry.get_active()
            api_key = provider.api_key
            api_base = provider.api_base
            model = provider.model

            original_system_prompt = self.symbix_client.system_prompt
            enriched = original_system_prompt or (
                "你是一个可靠的个人助理。用户通过定时任务派发给你一条指令,请完成它。"
            )
            # 定时任务模式的 system prompt 改为显式传参(不再写全局单例),
            # 否则任务备跑期间会与其他会话的 system prompt 互相覆盖。
            job_system_prompt = enriched + (
                "\n\n[定时任务模式]\n"
                "这次请求由定时任务触发,无人值守。如需要执行工具,只做安全的只读/无副作用操作;"
                "写入、删除、执行命令等需要人工确认的操作不要做,直接在回复里说明需要人工处理。"
            )
            # 时间必须显式告知:job 链路不像聊天链路会拼 dyn_parts,
            # 不注入的话模型连今天是几号都不知道,回复里的日期只能瞎编。
            job_system_prompt += "\n\n" + current_time_line()

            mcp_tools = self.tool_registry.get_openai_tools()
            import uuid as _uuid
            ckpt_round_id = _uuid.uuid4().hex[:12]
            start_ts = time.time()
            # 本次执行的总预算:所有模型调用(含工具轮)共享,用完就判失败并落历史
            run_deadline = start_ts + JOB_RUN_BUDGET

            steps = []
            last_reasoning = None

            response = await self._call_model(
                lambda: self.symbix_client.chat(
                    user_input=job["prompt"],
                    history=history[:-1],
                    registry=self.skill_registry,
                    tools=mcp_tools,
                    override_api_key=api_key,
                    override_api_base=api_base,
                    override_model=model,
                    system_prompt=job_system_prompt,
                    system_tail=UNATTENDED_SYSTEM_TAIL,
                    read_timeout=JOB_READ_TIMEOUT,
                ),
                deadline=run_deadline,
            )
            last_reasoning = response.get("reasoning")

            max_tool_rounds = 25
            round_count = 0
            write_counts: dict[str, int] = {}
            NONSTREAM_WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                                     "delete_file", "create_skill", "run_command",
                                     "open_terminal"}
            MAX_WRITE = 3

            final_text = response["content"] or ""

            while response.get("tool_calls") and round_count < max_tool_rounds:
                round_count += 1
                tool_results = []

                for tc in response["tool_calls"]:
                    fn = tc  # dict: {id, name, arguments}
                    try:
                        args = _json.loads(fn.get("arguments")) if isinstance(fn.get("arguments"), str) else fn.get("arguments")
                    except Exception:
                        args = {}

                    # 频次反循环
                    if fn["name"] in NONSTREAM_WRITE_TOOLS:
                        write_counts[fn["name"]] = write_counts.get(fn["name"], 0) + 1
                        if write_counts[fn["name"]] > MAX_WRITE:
                            stop_hint = (
                                f"[System] 工具 `{fn['name']}` 已被调用 {write_counts[fn['name']] - 1} 次。"
                                "请停止重复调用,直接向用户总结已完成的工作,不要继续调用任何写入类工具。"
                            )
                            tool_results.append({"tool_call_id": fn["id"], "role": "tool", "name": fn["name"],
                                                 "content": stop_hint, "arguments": fn.get("arguments")})
                            response = {"content": stop_hint, "tool_calls": None, "reasoning": last_reasoning}
                            break

                    _risk = classify_tool_risk(fn["name"], args)
                    risk_level, risk_reason = _risk.level, _risk.reason

                    # 后台无人值守:不派发子 Agent(耗 token 且无进度出口,失败无感知)
                    # 注意 delegate_task 和批量版 delegate_tasks 都要拦
                    if fn["name"] in ("delegate_task", "delegate_tasks"):
                        skip_msg = "[系统] 定时任务中不派发子 Agent,请直接使用只读工具完成任务。"
                        tool_results.append({"tool_call_id": fn["id"], "role": "tool", "name": fn["name"],
                                             "content": skip_msg, "arguments": fn.get("arguments")})
                        steps.append({"type": "tool_result", "tool_call_id": fn["id"], "name": fn["name"],
                                      "content": skip_msg})
                        continue

                    # 无人值守不能提问/等确认:直接回一句「自行决定」,避免任务卡在等人回答
                    if fn["name"] in UNATTENDED_BLOCKED_TOOLS:
                        skip_msg = (
                            "[系统] 定时任务无人值守,没有用户可回答:请自行选择最合理的做法继续执行,"
                            "把需要用户知晓的事直接写进最终回复。"
                        )
                        tool_results.append({"tool_call_id": fn["id"], "role": "tool", "name": fn["name"],
                                             "content": skip_msg, "arguments": fn.get("arguments")})
                        steps.append({"type": "tool_result", "tool_call_id": fn["id"], "name": fn["name"],
                                      "content": skip_msg})
                        continue

                    # 后台无人审批策略:定时任务一律只跑 SAFE 工具,
                    # MEDIUM/HIGH 跳过并在 memory 里留痕(用户下次开聊可手动重跑)
                    if risk_level != ToolRiskLevel.SAFE:
                        skip_msg = (
                            f"[需人工处理] 定时任务自动跳过工具 {fn['name']}（风险等级 {risk_level}）：{risk_reason}。"
                            f"请用户在界面上手动执行并确认。"
                        )
                        tool_results.append({"tool_call_id": fn["id"], "role": "tool", "name": fn["name"],
                                             "content": skip_msg, "arguments": fn.get("arguments")})
                        steps.append({"type": "tool_result", "tool_call_id": fn["id"], "name": fn["name"],
                                      "content": skip_msg})
                        continue

                    _ctx_set_current(sid, ckpt_round_id)
                    # 异步工具(delegate_task 类)必须 await,否则拿到的是 coroutine
                    if self.tool_registry.is_async_tool(fn["name"]):
                        out = await self.tool_registry.execute_async(fn["name"], fn.get("arguments"))
                    else:
                        out = self.tool_registry.execute(fn["name"], fn.get("arguments"))
                    if not isinstance(out, str):
                        out = _json.dumps(out, ensure_ascii=False)
                    tool_results.append({"tool_call_id": fn["id"], "role": "tool", "name": fn["name"],
                                         "content": out, "arguments": fn.get("arguments")})
                    steps.append({"type": "tool_result", "tool_call_id": fn["id"], "name": fn["name"],
                                  "content": out})

                response = await self._call_model(
                    lambda: self.symbix_client.chat_with_tool_results(
                        user_input=job["prompt"],
                        history=history[:-1],
                        registry=self.skill_registry,
                        tools=mcp_tools,
                        tool_results=tool_results,
                        override_api_key=api_key,
                        override_api_base=api_base,
                        override_model=model,
                        system_prompt=job_system_prompt,
                        system_tail=UNATTENDED_SYSTEM_TAIL,
                        # thinking 模式的上游要求把上一轮 reasoning 原样回传,否则 400
                        reasoning=last_reasoning,
                        read_timeout=JOB_READ_TIMEOUT,
                    ),
                    deadline=run_deadline,
                )
                last_reasoning = response.get("reasoning")
                final_text = response.get("content") or final_text

            output_snippet = (final_text or "")[:200]
            output_full = final_text or ""
            self.memory.add(sid, "assistant", final_text or "")

            self.checkpoint_recorder.emit_round(
                session_id=sid, round_id=ckpt_round_id,
                user_msg=job["prompt"], assistant_text=final_text or "",
                reasoning=last_reasoning or "", tool_count=len(steps), failed_tools=0,
                duration_ms=int((time.time() - start_ts) * 1000),
            )

            self.storage.update_status(job_id, "ok", None, run_time)
            self.storage.add_history(job_id, run_time, "ok", output_full or "")
            self._notify(job, final_text or "", "ok")
            return "ok"
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.storage.update_status(job_id, "error", str(e), run_time)
            # 失败也必须落历史 + 通知:以前 add_history 抛 UnboundLocalError,
            # 结果历史表空、用户连一条「提醒失败了」的提示都收不到。
            try:
                self.storage.add_history(job_id, run_time, "error",
                                         output_full or output_snippet or "", str(e) or "")
            except Exception:
                traceback.print_exc()
            if report:
                self._notify(job, str(e), "error")
            return "error"

    async def _call_model(self, factory, attempts: int = JOB_MODEL_ATTEMPTS,
                          deadline: float | None = None) -> dict:
        """调模型并在上游抖动时重试**整次调用**,同时给单次调用与整轮任务设硬上限。

        wait_for 会在上游不发数据时打断本次调用(取消内层流与重试),
        避免把默认 300s 读超时一层层白等满;预算用尽就不再重试,直接判失败。
        """
        stop_at = min(deadline if deadline else float("inf"), time.time() + JOB_CALL_BUDGET)
        last: Exception | None = None
        for i in range(1, attempts + 1):
            remaining = stop_at - time.time()
            if remaining <= 1:
                raise RuntimeError(f"{last}; 且已用尽模型调用时间预算" if last else "已用尽模型调用时间预算")
            per_call = min(JOB_CALL_TIMEOUT, remaining)
            try:
                response = await asyncio.wait_for(factory(), timeout=per_call)
                _raise_if_upstream_failed(response)
                return response
            except asyncio.TimeoutError:
                last = RuntimeError(f"模型调用超时(超过 {per_call:.0f}s 无输出)")
            except RuntimeError as e:
                last = e
            if i < attempts:
                delay = JOB_RETRY_BASE_DELAY * i
                print(f"[job] 模型调用第 {i}/{attempts} 次失败,{delay:.0f}s 后重试: {last}")
                await asyncio.sleep(delay)
        raise last if last else RuntimeError("模型调用失败")

    def _notify(self, job: dict, snippet: str, status: str) -> None:
        """通过 pet_action 发一条事件(桌宠表情/通知)。失败不阻断。"""
        try:
            self.pet_action.emit(
                "scheduled_job",
                bubble=f"[{job.get('name', '')}] {snippet[:60]}",
                source="schedule",
                extra={
                    "job_id": job["id"],
                    "name": job.get("name", ""),
                    "status": status,
                    "snippet": snippet[:80],
                },
            )
        except Exception:
            pass