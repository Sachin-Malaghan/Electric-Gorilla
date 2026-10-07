"""The bounded agent loop (spec 6).

    UNDERSTANDING -> PLANNING -> RETRIEVE_CONTEXT -> [ SELECT_ACTION -> CALL_TOOL -> OBSERVE
        -> (VERIFY | RECOVER) ]* -> REPORT

There is no unbounded `while True -> ask LLM`: every iteration first checks cancellation /
pause, max iterations, wall-clock time, token budget, cost budget (agent and task), the
tool-call limit and repeated-error detection. Exceeding any of them ends the run with a
typed outcome the workflow can escalate. The LLM decides *what* to do; this code decides
whether it is *allowed* to and when to stop.

A run finishes only through the `submit_report` tool, whose input schema is the role's
report model - so every agent result is a validated, structured payload (spec 10).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from shunya.core.agent_runtime.control import RunCancelled, RunControl
from shunya.core.agent_runtime.prompts import PromptComposer
from shunya.core.agent_runtime.registry import AgentStatusService
from shunya.core.interfaces import IEventBus, IModelProvider
from shunya.core.memory import MemoryService
from shunya.core.models import ChatMessage, ModelProviderError, ModelRouter, ToolResultBlock, cost_usd
from shunya.core.permissions import WorkspaceSandbox
from shunya.core.persistence import Store
from shunya.core.task_engine import TaskService
from shunya.shared.schemas import (
    AgentProfile,
    AgentRun,
    AgentState,
    CostRecord,
    Event,
    EventType,
    MemoryKind,
    MemoryRecord,
    RunPhase,
    RunStatus,
    Task,
    ToolCallRecord,
    utcnow,
)
from shunya.tools.base import Tool, ToolContext, ToolRegistry, ToolResult
from shunya.tools.services import ToolServices

log = logging.getLogger(__name__)

REPEATED_ERROR_LIMIT = 3
MAX_NUDGES = 2
MAX_PROVIDER_FAILURES = 3
_ID = re.compile(r"\b[A-Z]{1,5}-[0-9a-f]{10}\b|\b\d+(\.\d+)?s\b")


class _SubmitReport(Tool):
    name = "submit_report"
    description = (
        "Finish your work by submitting your final structured report. Call this exactly once, "
        "when the work is complete (or when you are certain you cannot complete it - say so honestly in the report)."
    )
    activity = AgentState.REPORTING

    def __init__(self, model: type[BaseModel]):
        self.Input = model  # type: ignore[misc]

    def describe_call(self, args: BaseModel) -> str:
        return "Writing report"

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        return ToolResult(content="Report accepted.", summary="Submitted report", data=args.model_dump(mode="json"), terminal=True)


@dataclass
class RunRequest:
    agent: AgentProfile
    purpose: str
    brief: str
    output_model: type[BaseModel]
    control: RunControl
    task: Task | None = None
    sandbox: WorkspaceSandbox | None = None
    work_description: str = ""
    location: str = "desk"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunOutcome:
    run: AgentRun
    report: BaseModel | None = None

    @property
    def ok(self) -> bool:
        return self.run.status == RunStatus.SUCCEEDED and self.report is not None


class _Stop(Exception):
    def __init__(self, status: RunStatus, reason: str):
        self.status, self.reason = status, reason


class AgentRunner:
    def __init__(
        self,
        *,
        provider: IModelProvider,
        router: ModelRouter,
        registry: ToolRegistry,
        services: ToolServices,
        store: Store,
        bus: IEventBus,
        statuses: AgentStatusService,
        composer: PromptComposer,
        tasks: TaskService,
        memory: MemoryService,
        spend: Any = None,
    ):
        self.provider = provider
        self.router = router
        self.registry = registry
        self.services = services
        self.store = store
        self.bus = bus
        self.statuses = statuses
        self.composer = composer
        self.tasks = tasks
        self.memory = memory
        self.spend = spend  # SpendMeter: the studio-wide cap on model spend

    # ------------------------------------------------------------------ helpers

    async def _phase(self, run: AgentRun, phase: RunPhase) -> None:
        run.phase = phase
        self.store.runs.put(run)

    def _check_limits(self, req: RunRequest, run: AgentRun, started: float) -> None:
        a, t = req.agent, req.task
        if self.spend is not None and self.spend.exhausted:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"the studio's model spending cap (${self.spend.limit_usd:.2f}) is reached; the owner must raise it to continue")
        if run.iterations >= a.max_iterations:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"max iterations ({a.max_iterations}) reached")
        if time.monotonic() - started > a.max_runtime_s:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"max runtime ({a.max_runtime_s}s) reached")
        if run.input_tokens + run.output_tokens > a.token_budget:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"token budget ({a.token_budget}) exhausted")
        if run.cost_usd > a.cost_budget:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"agent cost budget (${a.cost_budget:.2f}) exhausted")
        if run.tool_calls >= a.max_tool_calls:
            raise _Stop(RunStatus.BUDGET_EXCEEDED, f"tool-call limit ({a.max_tool_calls}) reached")
        if t is not None:
            if t.cost_usd > t.budget.max_cost_usd:
                raise _Stop(RunStatus.BUDGET_EXCEEDED, f"task cost budget (${t.budget.max_cost_usd:.2f}) exhausted")
            if t.llm_calls >= t.budget.max_llm_calls:
                raise _Stop(RunStatus.BUDGET_EXCEEDED, f"task LLM-call budget ({t.budget.max_llm_calls}) exhausted")

    @staticmethod
    def _fingerprint(tool: str, result: ToolResult) -> str:
        errors = result.data.get("errors") if result.data else None
        if errors:
            keys = sorted(f"{e.get('code', '')}:{str(e.get('file', '')).rsplit('/', 1)[-1]}:{str(e.get('message', ''))[:80]}" for e in errors)
            return f"{tool}:" + "|".join(keys)[:600]
        return f"{tool}:{_ID.sub('', result.content)[:200]}"

    # ------------------------------------------------------------------ main loop

    async def run(self, req: RunRequest) -> RunOutcome:
        agent, task = req.agent, req.task
        config = self.router.resolve(agent.model, req.work_description)
        run = AgentRun(
            agent_id=agent.id, task_id=task.id if task else None, trace_id=task.trace_id if task else None,
            purpose=req.purpose, model=config.model or "", phase=RunPhase.UNDERSTANDING,
        )
        self.store.runs.put(run)
        await self.bus.publish(
            Event(type=EventType.AGENT_STARTED, agent_id=agent.id, task_id=run.task_id, run_id=run.id, trace_id=run.trace_id,
                  payload={"purpose": req.purpose, "model": config.model, "effort": config.effort})
        )
        submit = _SubmitReport(req.output_model)
        specs = self.registry.specs_for(agent, extra=[submit])
        system = self.composer.compose(agent)
        messages: list[ChatMessage] = [ChatMessage(role="user", text=req.brief)]
        debugging = False

        async def set_activity(state: AgentState, action: str) -> None:
            if debugging and state == AgentState.CODING:
                state = AgentState.DEBUGGING
            location = {AgentState.TESTING: "qa_lab", AgentState.PLANNING: "whiteboard"}.get(state, req.location)
            await self.statuses.set(agent.id, state, action=action, location=location, trace_id=run.trace_id)

        ctx = ToolContext(agent=agent, run=run, services=self.services, task=task, sandbox=req.sandbox, set_activity=set_activity, extra=req.extra)
        await self.statuses.set(agent.id, AgentState.UNDERSTANDING, action=f"Reading the brief: {req.purpose}", task_id=run.task_id, run_id=run.id, location=req.location, trace_id=run.trace_id)

        started = time.monotonic()
        errors: Counter[str] = Counter()
        nudges = provider_failures = 0
        report: BaseModel | None = None
        status, reason = RunStatus.SUCCEEDED, ""
        try:
            await self._phase(run, RunPhase.PLANNING)
            await self.statuses.set(agent.id, AgentState.PLANNING, action="Planning the approach", location="whiteboard" if req.location == "desk" else req.location, trace_id=run.trace_id)
            await self._phase(run, RunPhase.RETRIEVE_CONTEXT)
            while report is None:
                # Always yield once per iteration: a provider or tool that completes without
                # suspending must not starve the event loop (API, WebSocket, pause/cancel).
                await asyncio.sleep(0)
                await req.control.checkpoint()
                self._check_limits(req, run, started)
                run.iterations += 1
                await self._phase(run, RunPhase.SELECT_ACTION)
                remaining = max(5.0, agent.max_runtime_s - (time.monotonic() - started))
                try:
                    resp = await asyncio.wait_for(
                        self.provider.generate(system=system, messages=messages, tools=specs, config=config, agent_id=agent.id), remaining
                    )
                except TimeoutError:
                    raise _Stop(RunStatus.BUDGET_EXCEEDED, f"max runtime ({agent.max_runtime_s}s) reached during a model call") from None
                except ModelProviderError as e:
                    provider_failures += 1
                    if provider_failures >= MAX_PROVIDER_FAILURES:
                        raise _Stop(RunStatus.FAILED, f"model provider failed {provider_failures} times: {e}") from None
                    await asyncio.sleep(min(2.0 * provider_failures, 5.0))
                    continue
                await self._account(run, task, agent, resp)
                if resp.stop_reason == "refusal":
                    raise _Stop(RunStatus.ESCALATED, f"the model declined this request ({resp.stop_detail or 'no category'})")
                messages.append(resp.as_assistant_message())

                if not resp.tool_calls:
                    nudges += 1
                    if nudges > MAX_NUDGES:
                        raise _Stop(RunStatus.ESCALATED, "agent stopped without submitting a report")
                    messages.append(ChatMessage(role="user", text="Continue. When the work is complete, finish by calling the submit_report tool."))
                    continue

                truncated = resp.stop_reason == "max_tokens"
                results: list[ToolResultBlock] = []
                for tc in resp.tool_calls:
                    await asyncio.sleep(0)
                    await req.control.checkpoint()
                    if truncated:
                        result, latency = ToolResult(ok=False, content="NOT EXECUTED: your response hit the output limit. Retry in smaller steps.", summary=f"{tc.name} skipped (truncated response)"), 0
                    elif run.tool_calls >= agent.max_tool_calls:
                        raise _Stop(RunStatus.BUDGET_EXCEEDED, f"tool-call limit ({agent.max_tool_calls}) reached")
                    else:
                        await self._phase(run, RunPhase.CALL_TOOL)
                        result, latency = await self.registry.execute(ctx, tc.name, tc.arguments, extra={submit.name: submit})
                    run.tool_calls += 1
                    await self._record_tool(run, agent, tc.name, tc.arguments, result, latency)
                    await self._phase(run, RunPhase.OBSERVE)
                    results.append(ToolResultBlock(tool_call_id=tc.id, content=result.content, is_error=not result.ok))
                    if result.ok:
                        if tc.name == "compile_project":
                            debugging = False
                        if result.terminal:
                            await self._phase(run, RunPhase.VERIFY)
                            report = req.output_model.model_validate(result.data)
                    else:
                        await self._phase(run, RunPhase.RECOVER)
                        if tc.name in ("compile_project", "run_automation_tests"):
                            debugging = True
                        fp = self._fingerprint(tc.name, result)
                        errors[fp] += 1
                        if errors[fp] >= REPEATED_ERROR_LIMIT:
                            messages.append(ChatMessage(role="user", tool_results=results))
                            raise _Stop(RunStatus.ESCALATED, f"the same error occurred {errors[fp]} times: {result.summary}")
                messages.append(ChatMessage(role="user", tool_results=results))
            await self._phase(run, RunPhase.REPORT)
        except _Stop as stop:
            status, reason = stop.status, stop.reason
        except RunCancelled:
            status, reason = RunStatus.CANCELLED, "cancelled by user"
        except asyncio.CancelledError:
            status, reason = RunStatus.INTERRUPTED, "studio shut down"
            await self._finish(req, run, status, reason, report)
            raise
        except Exception as e:  # noqa: BLE001 - a runtime bug must surface as a failed run, not a hung task
            log.exception("agent run crashed")
            status, reason = RunStatus.FAILED, f"runtime error: {type(e).__name__}: {e}"
        await self._finish(req, run, status, reason, report)
        return RunOutcome(run=run, report=report if status == RunStatus.SUCCEEDED else None)

    # ------------------------------------------------------------------ bookkeeping

    async def _account(self, run: AgentRun, task: Task | None, agent: AgentProfile, resp) -> None:
        model = resp.model or run.model
        cost = cost_usd(model, resp.usage)
        run.llm_calls += 1
        run.input_tokens += resp.usage.input_tokens + resp.usage.cache_read_tokens + resp.usage.cache_write_tokens
        run.output_tokens += resp.usage.output_tokens
        run.cost_usd = round(run.cost_usd + cost, 6)
        if self.spend is not None:
            self.spend.add(cost)
        run.model = model
        self.store.runs.put(run)
        self.store.cost_records.put(
            CostRecord(
                run_id=run.id, task_id=run.task_id, agent_id=agent.id, model=model, input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens, cache_read_tokens=resp.usage.cache_read_tokens, cost_usd=cost,
            )
        )
        if task is not None:
            task.cost_usd = round(task.cost_usd + cost, 6)
            task.llm_calls += 1
            task.tokens += resp.usage.total
            self.tasks.save(task)
        await self.bus.publish(
            Event(type=EventType.COST_RECORDED, agent_id=agent.id, task_id=run.task_id, run_id=run.id, trace_id=run.trace_id,
                  payload={"model": model, "tokens": resp.usage.total, "cost_usd": round(cost, 6), "run_cost_usd": run.cost_usd})
        )

    async def _record_tool(self, run: AgentRun, agent: AgentProfile, name: str, arguments: dict[str, Any], result: ToolResult, latency: int) -> None:
        for f in result.files_read:
            if f not in run.files_inspected:
                run.files_inspected.append(f)
        for f in result.files_written:
            if f not in run.files_modified:
                run.files_modified.append(f)
        self.store.runs.put(run)
        redacted = {k: (v if len(str(v)) <= 400 else f"{str(v)[:400]}... [{len(str(v))} chars]") for k, v in (arguments or {}).items()}
        record = ToolCallRecord(
            run_id=run.id, agent_id=agent.id, task_id=run.task_id, trace_id=run.trace_id, tool=name, arguments=redacted,
            ok=result.ok, summary=result.summary, error=None if result.ok else result.content[:2000], latency_ms=latency,
        )
        self.store.tool_calls.put(record)
        await self.bus.publish(
            Event(type=EventType.AGENT_TOOL_CALLED, agent_id=agent.id, task_id=run.task_id, run_id=run.id, trace_id=run.trace_id,
                  payload={"tool": name, "ok": result.ok, "summary": result.summary, "latency_ms": latency, "tool_call_id": record.id})
        )

    async def _finish(self, req: RunRequest, run: AgentRun, status: RunStatus, reason: str, report: BaseModel | None) -> None:
        agent = req.agent
        run.status = status
        run.error = reason or None
        run.ended_at = utcnow()
        run.phase = RunPhase.REPORT if status == RunStatus.SUCCEEDED else RunPhase.IDLE
        if report is not None:
            run.report = report.model_dump(mode="json")
        self.store.runs.put(run)
        base = dict(agent_id=agent.id, task_id=run.task_id, run_id=run.id, trace_id=run.trace_id)
        stats = {"iterations": run.iterations, "tool_calls": run.tool_calls, "cost_usd": run.cost_usd, "purpose": req.purpose}
        if status == RunStatus.SUCCEEDED:
            await self.statuses.set(agent.id, AgentState.SUCCESS, action=f"Finished: {req.purpose}", location=req.location, trace_id=run.trace_id)
            await self.bus.publish(Event(type=EventType.AGENT_COMPLETED, payload=stats, **base))
        elif status in (RunStatus.CANCELLED, RunStatus.INTERRUPTED):
            await self.statuses.set(agent.id, AgentState.IDLE, action="", task_id=None, run_id=None, location="desk", trace_id=run.trace_id)
            await self.bus.publish(Event(type=EventType.AGENT_FAILED, payload={**stats, "status": status, "reason": reason}, **base))
        elif status in (RunStatus.ESCALATED, RunStatus.BUDGET_EXCEEDED):
            await self.statuses.set(agent.id, AgentState.BLOCKED, action=f"Escalated: {reason}", location=req.location, trace_id=run.trace_id)
            await self.bus.publish(
                Event(type=EventType.AGENT_ESCALATED, payload={**stats, "status": status, "reason": reason, "escalate_to": agent.escalation_policy.escalate_to or agent.supervisor}, **base)
            )
        else:
            await self.statuses.set(agent.id, AgentState.FAILED, action=f"Failed: {reason}", location=req.location, trace_id=run.trace_id)
            await self.bus.publish(Event(type=EventType.AGENT_FAILED, payload={**stats, "status": status, "reason": reason}, **base))
        if status not in (RunStatus.CANCELLED, RunStatus.INTERRUPTED):
            summary = ""
            if report is not None:
                summary = str(run.report.get("summary", ""))[:600]
            self.memory.remember(
                MemoryRecord(
                    kind=MemoryKind.EPISODIC, agent_id=agent.id, task_id=run.task_id,
                    title=f"{req.purpose} on {run.task_id or 'no task'}: {status}",
                    content=(summary or reason or "no summary")[:800],
                    tags=[req.purpose, str(status), *run.files_modified[:8]],
                )
            )
