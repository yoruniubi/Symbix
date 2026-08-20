"""Job runner：到点触发后，以非流式方式运行一轮 agent 对话。

复用 chat 主循环的组件（memory / tool_registry / symbix_client / checkpoint / pet_action），
但不落地 SSE，也不走前端审批——auto_safe=True 时只执行 SAFE 工具，MEDIUM/HIGH 跳过并记「需手动重跑」。
"""
from __future__ import annotations
import asyncio
import json as _json
import time
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: F401  (类型提示/复用)
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger


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

    async def execute(self, job: dict) -> None:
        """执行一次 job（由 scheduler._dispatch 调用）。"""
        from Symbix_sdk.checkpoint import set_current as _ctx_set_current
        from Symbix_sdk.checkpoint import get_recorder
        from Symbix_sdk.tools.risk_classifier import classify_tool_risk, ToolRiskLevel

        job_id = job["id"]
        sid = job.get("session_id")
        auto_safe = job.get("auto_safe", True)
        run_time = datetime.now()

        # 无 session → 自动建一个固定「定时任务」session（每个 job 长期复用，攒上下文）
        if not sid:
            sid = f"schedule__{job_id}"
            job["session_id"] = sid
            self.storage.upsert_meta(job)

        output_snippet = ""
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
            self.symbix_client.system_prompt = enriched + (
                "\n\n[定时任务模式]\n"
                "这次请求由定时任务触发,无人值守。如需要执行工具,只做安全的只读/无副作用操作;"
                "写入、删除、执行命令等需要人工确认的操作不要做,直接在回复里说明需要人工处理。"
            )

            mcp_tools = self.tool_registry.get_openai_tools()
            import uuid as _uuid
            ckpt_round_id = _uuid.uuid4().hex[:12]
            start_ts = time.time()

            steps = []
            last_reasoning = None

            response = await self.symbix_client.chat(
                user_input=job["prompt"],
                history=history[:-1],
                registry=self.skill_registry,
                tools=mcp_tools,
                override_api_key=api_key,
                override_api_base=api_base,
                override_model=model,
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
                    fn = tc.function
                    try:
                        args = _json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
                    except Exception:
                        args = {}

                    # 频次反循环
                    if fn.name in NONSTREAM_WRITE_TOOLS:
                        write_counts[fn.name] = write_counts.get(fn.name, 0) + 1
                        if write_counts[fn.name] > MAX_WRITE:
                            stop_hint = (
                                f"[System] 工具 `{fn.name}` 已被调用 {write_counts[fn.name] - 1} 次。"
                                "请停止重复调用,直接向用户总结已完成的工作,不要继续调用任何写入类工具。"
                            )
                            tool_results.append({"tool_call_id": tc.id, "role": "tool", "name": fn.name,
                                                 "content": stop_hint, "arguments": fn.arguments})
                            response = {"content": stop_hint, "tool_calls": None, "reasoning": last_reasoning}
                            break

                    risk_level, risk_reason = classify_tool_risk(fn.name, args)

                    # auto_safe:非 SAFE 跳过；否则非 SAFE 也跳过（后台无人审批，一律不执行写操作）
                    if risk_level != ToolRiskLevel.SAFE:
                        skip_msg = (
                            f"[需人工处理] 定时任务自动跳过工具 {fn.name}（风险等级 {risk_level}）：{risk_reason}。"
                            f"请用户在界面上手动执行并确认。"
                        )
                        tool_results.append({"tool_call_id": tc.id, "role": "tool", "name": fn.name,
                                             "content": skip_msg, "arguments": fn.arguments})
                        steps.append({"type": "tool_result", "tool_call_id": tc.id, "name": fn.name,
                                      "content": skip_msg})
                        continue

                    _ctx_set_current(sid, ckpt_round_id)
                    out = self.tool_registry.execute(fn.name, fn.arguments)
                    if not isinstance(out, str):
                        out = _json.dumps(out, ensure_ascii=False)
                    tool_results.append({"tool_call_id": tc.id, "role": "tool", "name": fn.name,
                                         "content": out, "arguments": fn.arguments})
                    steps.append({"type": "tool_result", "tool_call_id": tc.id, "name": fn.name,
                                  "content": out})

                response = await self.symbix_client.chat_with_tool_results(
                    user_input=job["prompt"],
                    history=history[:-1],
                    registry=self.skill_registry,
                    tools=mcp_tools,
                    tool_results=tool_results,
                    override_api_key=api_key,
                    override_api_base=api_base,
                    override_model=model,
                )
                last_reasoning = response.get("reasoning")
                final_text = response.get("content") or final_text

            output_snippet = (final_text or "")[:200]
            self.memory.add(sid, "assistant", final_text or "")

            self.checkpoint_recorder.emit_round(
                session_id=sid, round_id=ckpt_round_id,
                user_msg=job["prompt"], assistant_text=final_text or "",
                reasoning=last_reasoning or "", tool_count=len(steps), failed_tools=0,
                duration_ms=int((time.time() - start_ts) * 1000),
            )

            self.storage.update_status(job_id, "ok", None, run_time)
            self.storage.add_history(job_id, run_time, "ok", output_snippet or "")
            self._notify(job, final_text or "", "ok")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.storage.update_status(job_id, "error", str(e), run_time)
            self.storage.add_history(job_id, run_time, "error", output_snippet or "", str(e)[:300])
            self._notify(job, str(e), "error")
        finally:
            if 'original_system_prompt' in locals():
                self.symbix_client.system_prompt = original_system_prompt

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