"""Studio Orchestrator / Workflow Engine (spec 3, 8, 20, 38, 48).

    Director -> Producer (planning meeting) -> task graph
    per task:  Programmer -> Reviewer -> Build -> QA -> Human approval -> merge to develop

The workflow is deterministic code driven by the persisted task status: each loop turn
looks at `task.status` and runs the step for that status. That makes it restartable -
after a crash the same loop continues from whatever status is in the database - and it
keeps authority out of the LLM: agents produce reports, this code decides transitions.

Independence (spec 38): the reviewer and QA are different agents from the implementer,
QA re-runs the tests itself, and a QA "PASS" without a passing test run recorded by the
test service during that QA step is rejected by code.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from shunya.config import Settings
from shunya.core.agent_runtime import (
    AgentRegistry,
    AgentRunner,
    AgentStatusService,
    ControlRegistry,
    RunCancelled,
    RunOutcome,
    RunRequest,
)
from shunya.core.interfaces import IEventBus
from shunya.core.memory import MemoryService
from shunya.core.orchestration import reports as r
from shunya.core.orchestration.approvals import ApprovalService, assess_risk
from shunya.core.permissions import WorkspaceSandbox
from shunya.core.persistence import Store
from shunya.core.task_engine import ACTIVE_STATUSES, TaskService
from shunya.knowledge import HybridRetriever
from shunya.shared.schemas import (
    AgentMessage,
    AgentProfile,
    AgentState,
    Approval,
    ApprovalStatus,
    ArtifactType,
    Bug,
    BuildStatus,
    CollaborationSession,
    Event,
    EventType,
    MemoryKind,
    MemoryRecord,
    MessageType,
    Priority,
    RiskLevel,
    RunStatus,
    Severity,
    Task,
    TaskStatus,
    TaskType,
    utcnow,
)
from shunya.tools.git_tools import GitError
from shunya.tools.services import ToolServices

log = logging.getLogger(__name__)
S = TaskStatus


class StepBlocked(Exception):
    """A step cannot proceed without a human (escalation)."""


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        bus: IEventBus,
        tasks: TaskService,
        registry: AgentRegistry,
        statuses: AgentStatusService,
        runner: AgentRunner,
        services: ToolServices,
        approvals: ApprovalService,
        memory: MemoryService,
        controls: ControlRegistry,
    ):
        self.settings = settings
        self.store = store
        self.bus = bus
        self.tasks = tasks
        self.registry = registry
        self.statuses = statuses
        self.runner = runner
        self.services = services
        self.approvals = approvals
        self.memory = memory
        self.controls = controls
        self._jobs: dict[str, asyncio.Task] = {}
        # Task objects owned by a running pipeline. API calls (pause, retry notes) must mutate
        # the same instance the pipeline saves, or its next save would overwrite them.
        self._live: dict[str, Task] = {}
        self._agent_locks: dict[str, asyncio.Lock] = {}
        self._slots = asyncio.Semaphore(settings.max_concurrent_tasks)

    # ================================================================== public API

    async def submit_feature(self, text: str, *, priority: Priority = Priority.MEDIUM, created_by: str = "user") -> Task:
        text = text.strip()
        if not text:
            raise ValueError("feature request is empty")
        feature = Task(
            id=self.tasks.repo.next_id("FEAT"), type=TaskType.FEATURE, title=text.splitlines()[0][:120],
            description=text, created_by=created_by, priority=priority,
        )
        await self.tasks.create(feature)
        self._spawn(feature.id, self._run_feature(feature.id))
        return feature

    async def cancel(self, task_id: str) -> Task:
        task = self._must_get(task_id)
        targets = [task] + [t for t in self.tasks.repo.list(parent_id=task_id)]
        for t in targets:
            self.controls.task(t.id).cancel()
        for t in targets:
            if t.id not in self._jobs or self._jobs[t.id].done():
                t = self._must_get(t.id)
                if t.status not in (S.DONE, S.CANCELLED):
                    await self._cancel_cleanup(t)
        return self._must_get(task_id)

    async def pause(self, task_id: str) -> Task:
        task = self._must_get(task_id)
        for t in [task] + self.tasks.repo.list(parent_id=task_id):
            self.controls.task(t.id).pause()
            t = self._must_get(t.id)
            t.paused = True
            self.tasks.save(t)
        await self.bus.publish(Event(type=EventType.AGENT_WAITING, task_id=task_id, payload={"paused": True, "by": "user"}))
        return self._must_get(task_id)

    async def resume(self, task_id: str) -> Task:
        task = self._must_get(task_id)
        for t in [task] + self.tasks.repo.list(parent_id=task_id):
            t = self._must_get(t.id)
            t.paused = False
            self.tasks.save(t)
            self.controls.task(t.id).resume()
        await self.bus.publish(Event(type=EventType.AGENT_STARTED, task_id=task_id, payload={"paused": False, "by": "user"}))
        return self._must_get(task_id)

    async def retry(self, task_id: str, note: str = "") -> Task:
        """Human un-blocks an escalated task: attempt counters reset and the pipeline resumes."""
        task = self._must_get(task_id)
        if task.status != S.BLOCKED:
            raise ValueError(f"{task_id} is {task.status}, only BLOCKED tasks can be retried")
        task.attempts = {}
        task.budget.max_cost_usd += max(task.cost_usd, 1.0)  # fresh headroom, explicitly granted by the human
        task.budget.max_llm_calls += task.llm_calls
        if note:
            task.feedback.append(f"[Human guidance] {note}")
        self.controls.reset_task(task.id)
        if task.type in (TaskType.FEATURE, TaskType.EPIC):
            children = self.tasks.repo.list(parent_id=task.id)
            await self.tasks.transition(task, S.IN_PROGRESS if children else S.BACKLOG, actor="user", reason="retry")
            for c in children:
                if c.status == S.BLOCKED:
                    await self.retry(c.id, note)
            self._spawn(task.id, self._run_feature(task.id))
        else:
            await self.tasks.transition(task, S.IN_PROGRESS if task.worktree else S.PLANNED, actor="user", reason="retry")
            parent = self.tasks.repo.get(task.parent_id) if task.parent_id else None
            if parent and parent.status == S.BLOCKED:
                self.controls.reset_task(parent.id)
                await self.tasks.transition(parent, S.IN_PROGRESS, actor="user", reason="child retried")
                self._spawn(parent.id, self._run_feature(parent.id))
            elif not parent:
                self._spawn(task.id, self._guarded(task.id, self._run_task(task.id)))
        return self._must_get(task_id)

    async def recover(self) -> int:
        """Restart recovery (spec 49): mark orphaned runs, then resume every active feature."""
        for run in self.store.runs.list(status=str(RunStatus.RUNNING), limit=1000):
            run.status, run.error, run.ended_at = RunStatus.INTERRUPTED, "studio restarted", utcnow()
            self.store.runs.put(run)
        for meeting in self.store.meetings.list(status="OPEN"):
            meeting.status, meeting.ended_at = "ABORTED", utcnow()
            self.store.meetings.put(meeting)
        resumed = 0
        for task in self.tasks.repo.list():
            if task.type not in (TaskType.FEATURE, TaskType.EPIC):
                continue
            if task.status in ACTIVE_STATUSES or task.status == S.AWAITING_APPROVAL:
                if task.paused:
                    for t in [task] + self.tasks.repo.list(parent_id=task.id):
                        self.controls.task(t.id).pause()
                self._spawn(task.id, self._run_feature(task.id))
                resumed += 1
        if resumed:
            await self.bus.publish(Event(type=EventType.STUDIO_RECOVERED, payload={"resumed_features": resumed}))
        return resumed

    async def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            job.cancel()
        await asyncio.gather(*self._jobs.values(), return_exceptions=True)

    def is_running(self, task_id: str) -> bool:
        job = self._jobs.get(task_id)
        return job is not None and not job.done()

    async def wait_idle(self, timeout: float | None = None) -> None:
        """Wait until no pipeline job is running (used by tests and the CLI demo)."""

        async def _wait() -> None:
            while any(not j.done() for j in self._jobs.values()):
                await asyncio.sleep(0.02)

        await asyncio.wait_for(_wait(), timeout)

    # ================================================================== plumbing

    def _must_get(self, task_id: str) -> Task:
        task = self._live.get(task_id) or self.tasks.repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _spawn(self, key: str, coro) -> None:
        existing = self._jobs.get(key)
        if existing and not existing.done():
            coro.close()
            return
        self._jobs[key] = asyncio.create_task(coro, name=f"pipeline:{key}")

    async def _guarded(self, task_id: str, coro) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("pipeline for %s crashed", task_id)

    def _agent(self, capability: str) -> AgentProfile:
        candidates = self.registry.with_capability(capability)
        if not candidates:
            raise StepBlocked(f"no enabled agent has capability '{capability}'")
        free = [a for a in candidates if not self._lock(a.id).locked()]
        return (free or candidates)[0]

    def _lock(self, agent_id: str) -> asyncio.Lock:
        return self._agent_locks.setdefault(agent_id, asyncio.Lock())

    async def _run_agent(self, req: RunRequest) -> RunOutcome:
        """One agent does one thing at a time."""
        async with self._lock(req.agent.id):
            outcome = await self.runner.run(req)
        if outcome.run.status == RunStatus.CANCELLED:
            raise RunCancelled()
        return outcome

    async def _idle(self, *agent_ids: str | None) -> None:
        for aid in agent_ids:
            if aid:
                await self.statuses.set(aid, AgentState.IDLE, action="", task_id=None, run_id=None, location="desk")

    async def _message(self, type: MessageType, sender: str, receiver: str, task: Task, summary: str, evidence: dict[str, Any] | None = None, severity: Severity = Severity.MEDIUM) -> AgentMessage:
        msg = AgentMessage(type=type, sender=sender, receiver=receiver, task_id=task.id, summary=summary, evidence=evidence or {}, severity=severity)
        self.store.messages.put(msg)
        await self.bus.publish(
            Event(type=EventType.MESSAGE_SENT, agent_id=sender, task_id=task.id, trace_id=task.trace_id,
                  payload={"message_id": msg.id, "type": type, "receiver": receiver, "summary": summary[:300], "severity": severity})
        )
        return msg

    async def _block(self, task: Task, reason: str, *, agent_id: str | None = None) -> None:
        """Escalate to a human: the task stops, the reason is recorded, the UI shows it."""
        if task.status in (S.DONE, S.CANCELLED):
            return
        task.result["blocked_reason"] = reason
        profile = self.registry.get(agent_id) if agent_id else None
        receiver = (profile.escalation_policy.escalate_to or profile.supervisor) if profile else None
        await self._message(MessageType.ESCALATION, agent_id or "orchestrator", receiver or "user", task, reason, severity=Severity.HIGH)
        if task.status != S.BLOCKED:
            await self.tasks.transition(task, S.BLOCKED, actor=agent_id or "orchestrator", reason=reason)
        if agent_id:
            await self.statuses.set(agent_id, AgentState.BLOCKED, action=f"Blocked: {reason[:120]}", task_id=task.id)

    async def _cancel_cleanup(self, task: Task) -> None:
        if task.status not in (S.DONE, S.CANCELLED):
            await self.tasks.transition(task, S.CANCELLED, actor="user", reason="cancelled by user")
        for approval in self.store.approvals.list(task_id=task.id, status=str(ApprovalStatus.PENDING)):
            await self.approvals.decide(approval.id, granted=False, decided_by="system", comment="task cancelled")
        if task.worktree:
            try:
                await self.services.git.remove_worktree(task.id)
            except GitError:
                log.warning("could not remove worktree for %s", task.id)
        for status in self.statuses.all():
            if status.task_id == task.id:
                await self._idle(status.id)

    def _sandbox(self, task: Task, agent: AgentProfile, *, writable: bool) -> WorkspaceSandbox:
        from pathlib import Path

        return WorkspaceSandbox(Path(task.worktree), writable_globs=agent.write_globs if writable else [], isolated=True)  # type: ignore[arg-type]

    def _roster(self) -> str:
        groups: dict[str, list[AgentProfile]] = {}
        for p in self.registry.all():
            if p.enabled and p.capability:
                groups.setdefault(p.capability, []).append(p)
        lines = []
        for cap, people in sorted(groups.items(), key=lambda kv: (kv[1][0].department, kv[0])):
            first = people[0]
            lines.append(f"- `{cap}` ({first.department}): {first.role} - {', '.join(first.responsibilities[:4])}")
        return "\n".join(lines)

    def _knowledge(self, root, query: str, max_chars: int = 7000) -> str:
        try:
            results = self.services.retriever_for(root).search(query, limit=6, max_chars=max_chars)
        except Exception:  # noqa: BLE001 - retrieval is best-effort context, never a reason to fail a task
            log.exception("knowledge retrieval failed")
            return ""
        return HybridRetriever.render(results)

    # ================================================================== feature pipeline

    async def _run_feature(self, feature_id: str) -> None:
        feature = self._must_get(feature_id)
        self._live[feature.id] = feature
        control = self.controls.task(feature.id)
        try:
            children = self.tasks.repo.list(parent_id=feature.id)
            if feature.status == S.BACKLOG or not children:
                await control.checkpoint()
                await self._plan_feature(feature)
                children = self.tasks.repo.list(parent_id=feature.id)
            if feature.status == S.PLANNED:
                await self.tasks.transition(feature, S.IN_PROGRESS, actor="producer", reason="task graph created")
            await self._execute_children(feature)
            feature = self._must_get(feature.id)
            children = self.tasks.repo.list(parent_id=feature.id)
            if all(c.status == S.DONE for c in children):
                feature.result["completed_tasks"] = [c.id for c in children]
                await self.tasks.transition(feature, S.DONE, actor="producer", reason="all tasks done")
            elif feature.status not in (S.CANCELLED, S.BLOCKED):
                stuck = [f"{c.id} is {c.status}" for c in children if c.status != S.DONE]
                await self._block(feature, "feature cannot complete: " + "; ".join(stuck))
        except RunCancelled:
            await self._cancel_cleanup(self._must_get(feature.id))
        except StepBlocked as e:
            await self._block(self._must_get(feature.id), str(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("feature pipeline crashed")
            await self._block(self._must_get(feature.id), f"orchestrator error: {type(e).__name__}: {e}")
        finally:
            self._live.pop(feature.id, None)

    async def _plan_feature(self, feature: Task) -> None:
        control = self.controls.task(feature.id)
        director = self._agent("director")
        producer = self._agent("producer")
        repo_sandbox = WorkspaceSandbox(self.settings.game_repo, writable_globs=[], isolated=False)
        knowledge = self._knowledge(self.settings.game_repo, feature.description, 5000)
        project_memory = self.memory.render(self.memory.recall(feature.description, kind=MemoryKind.PROJECT, limit=6))

        # 1. Studio Director interprets the objective.
        brief = feature.result.get("director_brief")
        if not brief:
            out = await self._run_agent(
                RunRequest(
                    agent=director, purpose="interpret feature request", control=self.controls.for_run(feature.id, director.id), task=feature,
                    sandbox=repo_sandbox, output_model=r.DirectorBrief, work_description=feature.description,
                    brief=_sections(
                        ("Feature request from the studio owner", feature.description),
                        ("Project decisions and standards", project_memory),
                        ("Your job", "Interpret this request as a game objective: what the player gains, what is in and out of scope, and the risks. "
                         "Do not design the implementation. Submit a DirectorBrief."),
                    ),
                )
            )
            if not out.ok:
                raise StepBlocked(f"Director could not interpret the request: {out.run.error}")
            brief = out.report.model_dump()  # type: ignore[union-attr]
            feature.result["director_brief"] = brief
            self.tasks.save(feature)
        await control.checkpoint()

        # 2. Planning meeting: Producer drafts the task graph, a programmer reviews feasibility.
        tech = self._agent("programmer")
        meeting = CollaborationSession(
            objective=f"Plan: {feature.title}", participants=[director.id, producer.id, tech.id], task_id=feature.id,
            shared_context=brief.get("summary", ""),
        )
        self.store.meetings.put(meeting)
        await self.bus.publish(
            Event(type=EventType.MEETING_STARTED, task_id=feature.id, trace_id=feature.trace_id,
                  payload={"meeting_id": meeting.id, "room": meeting.room, "participants": meeting.participants, "objective": meeting.objective})
        )
        loc = f"meeting:{meeting.room}"
        for pid in meeting.participants:
            await self.statuses.set(pid, AgentState.MEETING, action=meeting.objective, task_id=feature.id, location=loc)
        plan: r.FeaturePlan | None = None
        concerns: list[str] = []
        try:
            for round_no in range(2):
                out = await self._run_agent(
                    RunRequest(
                        agent=producer, purpose="plan feature into tasks", control=self.controls.for_run(feature.id, producer.id), task=feature,
                        sandbox=repo_sandbox, output_model=r.FeaturePlan, work_description=feature.description, location=loc,
                        brief=_sections(
                            ("Feature request", feature.description),
                            ("Director's brief", _bullets(brief)),
                            ("Engineering concerns to address in this revision", "\n".join(f"- {c}" for c in concerns)),
                            ("Relevant project knowledge", knowledge),
                            ("Studio roster (capabilities you can assign work to)", self._roster()),
                            ("Your job", "Break this feature into the smallest set of typed tasks the studio can deliver and verify. "
                             "Each task has a track: `code` (C++, compiled and tested - give a test_filter under 'ShunyaGame.'), "
                             "`doc` (documents under Docs/ - leave test_filter empty unless the author must run a playtest or the test suite), or "
                             "`content` (Unreal assets made with the content tools - leave test_filter empty). "
                             "Pick assignee_capability and reviewer_capability from the roster; the reviewer is a lead and never the assignee. "
                             "Order work with depends_on: design before the work it specifies, code before content that uses its classes, everything before QA. "
                             "Every task needs concrete acceptance criteria. Prefer one task when the feature is small. Submit a FeaturePlan."),
                        ),
                    )
                )
                if not out.ok:
                    raise StepBlocked(f"Producer could not produce a plan: {out.run.error}")
                plan = out.report  # type: ignore[assignment]
                await control.checkpoint()
                review = await self._run_agent(
                    RunRequest(
                        agent=tech, purpose="review plan feasibility", control=self.controls.for_run(feature.id, tech.id), task=feature,
                        sandbox=repo_sandbox, output_model=r.PlanReview, work_description=feature.description, location=loc,
                        brief=_sections(
                            ("Proposed plan", plan.model_dump_json(indent=1)),  # type: ignore[union-attr]
                            ("Relevant project knowledge", knowledge),
                            ("Your job", "You are in the planning meeting as the engineering voice. Check the plan against the actual codebase: "
                             "is it feasible, are acceptance criteria testable with Unreal automation tests, is anything missing? "
                             "Do not write code. Submit a PlanReview."),
                        ),
                    )
                )
                if not review.ok:
                    raise StepBlocked(f"plan review failed: {review.run.error}")
                pr: r.PlanReview = review.report  # type: ignore[assignment]
                meeting.decisions.append(f"Round {round_no + 1}: {pr.summary}")
                concerns = pr.concerns
                if pr.feasible or round_no == 1:
                    if not pr.feasible:
                        meeting.decisions.append("Proceeding with unresolved concerns recorded on the tasks.")
                    break
            assert plan is not None
            meeting.decisions.append(f"Plan accepted: {plan.summary}")
            meeting.action_items = [t.title for t in plan.tasks]
        finally:
            meeting.status, meeting.ended_at = "CLOSED", utcnow()
            self.store.meetings.put(meeting)
            await self.bus.publish(
                Event(type=EventType.MEETING_ENDED, task_id=feature.id, trace_id=feature.trace_id,
                      payload={"meeting_id": meeting.id, "participants": meeting.participants, "decisions": meeting.decisions, "action_items": meeting.action_items})
            )
            await self._idle(*meeting.participants)

        self.services.artifacts.put(type=ArtifactType.FEATURE_PLAN, title=f"Plan for {feature.id}", creator=producer.id, task_id=feature.id,
                                    content=plan.model_dump_json(indent=2), content_type="application/json")
        self.services.artifacts.put(type=ArtifactType.MEETING_NOTES, title=f"Planning meeting {meeting.id}", creator=producer.id, task_id=feature.id,
                                    content=meeting.model_dump_json(indent=2), content_type="application/json")

        # 3. Typed tasks with acceptance criteria.
        created: list[Task] = []
        for p in plan.tasks:
            task = Task(
                id=self.tasks.repo.next_id("GAME"), type=TaskType(p.type), title=p.title, description=p.description,
                created_by=producer.id, priority=Priority(p.priority), parent_id=feature.id, acceptance_criteria=p.acceptance_criteria,
                track=p.track,
                # an unknown capability falls back to the engineering defaults rather than stalling the task
                assignee_capability=p.assignee_capability if self.registry.with_capability(p.assignee_capability) else "programmer",
                review_capability=p.reviewer_capability if self.registry.with_capability(p.reviewer_capability) else "reviewer",
                test_filter=(p.test_filter if p.test_filter.startswith("ShunyaGame") else "ShunyaGame") if p.track == "code" else p.test_filter,
                trace_id=feature.trace_id,
            )
            if concerns:
                task.feedback.append("[Planning concerns] " + "; ".join(concerns))
            created.append(task)
        for task, p in zip(created, plan.tasks):
            task.dependencies = [created[i].id for i in p.depends_on if 0 <= i < len(created) and created[i].id != task.id]
            await self.tasks.create(task)
            await self.tasks.transition(task, S.PLANNED, actor=producer.id, reason="planned")
        feature.title = plan.epic_title or feature.title
        feature.result["plan_summary"] = plan.summary
        await self.tasks.transition(feature, S.PLANNED, actor=producer.id, reason=f"{len(created)} task(s) planned")

    async def _execute_children(self, feature: Task) -> None:
        running: dict[str, asyncio.Task] = {}
        while True:
            await self.controls.task(feature.id).checkpoint()
            children = self.tasks.repo.list(parent_id=feature.id)
            by_id = {c.id: c for c in children}
            for c in children:
                if (c.id in running and not running[c.id].done()) or c.status in (S.DONE, S.CANCELLED, S.BLOCKED):
                    continue
                if all(by_id[d].status == S.DONE for d in c.dependencies if d in by_id):
                    running[c.id] = asyncio.create_task(self._guarded(c.id, self._run_task(c.id)), name=f"task:{c.id}")
                    self._jobs[c.id] = running[c.id]
            active = [t for t in running.values() if not t.done()]
            if not active:
                children = self.tasks.repo.list(parent_id=feature.id)
                startable = [
                    c for c in children
                    if c.status not in (S.DONE, S.CANCELLED, S.BLOCKED)
                    and all(by_id[d].status == S.DONE for d in c.dependencies if d in by_id)
                ]
                if not startable:
                    return
                continue
            await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

    # ================================================================== task pipeline

    async def _run_task(self, task_id: str) -> None:
        task = self._must_get(task_id)
        self._live[task.id] = task
        control = self.controls.task(task.id)
        try:
            async with self._slots:
                while True:
                    await control.checkpoint()
                    match task.status:
                        case S.BACKLOG:
                            await self.tasks.transition(task, S.PLANNED, actor="producer")
                        case S.PLANNED:
                            owner = self._agent(task.assignee_capability)
                            await self.tasks.assign(task, owner.id, actor="producer")
                            await self._message(MessageType.TASK_HANDOFF, "producer_01", owner.id, task, f"Please implement: {task.title}",
                                                {"acceptance_criteria": task.acceptance_criteria})
                        case S.ASSIGNED:
                            branch, path = await self.services.git.create_worktree(task.id)
                            task.branch, task.worktree = branch, str(path)
                            await self.tasks.transition(task, S.IN_PROGRESS, actor=task.owner or "orchestrator", reason=f"isolated workspace {branch}")
                        case S.IN_PROGRESS:
                            await self._step_implement(task)
                        case S.REVIEW:
                            await self._step_review(task)
                        case S.CHANGES_REQUESTED:
                            await self.tasks.transition(task, S.IN_PROGRESS, actor=task.owner or "orchestrator", reason="addressing review feedback")
                        case S.BUILD:
                            await self._step_build(task)
                        case S.QA:
                            await self._step_qa(task)
                        case S.FAILED:
                            await self._step_failed(task)
                        case S.BUG_CREATED:
                            await self.tasks.transition(task, S.IN_PROGRESS, actor=task.owner or "orchestrator", reason="fixing reported defect")
                        case S.ACCEPTED:
                            await self._step_request_approval(task)
                        case S.AWAITING_APPROVAL:
                            await self._step_await_approval(task)
                        case S.REJECTED:
                            await self.tasks.transition(task, S.IN_PROGRESS, actor="user", reason="rework requested by human")
                        case S.DONE | S.CANCELLED | S.BLOCKED:
                            return
        except RunCancelled:
            await self._cancel_cleanup(self._must_get(task.id))
        except StepBlocked as e:
            await self._block(task, str(e), agent_id=task.owner)
        except GitError as e:
            await self._block(task, f"git error: {e}", agent_id=task.owner)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("task pipeline crashed")
            await self._block(task, f"orchestrator error: {type(e).__name__}: {e}", agent_id=task.owner)
        finally:
            self._live.pop(task.id, None)

    def _bump(self, task: Task, key: str) -> int:
        task.attempts[key] = task.attempts.get(key, 0) + 1
        self.tasks.save(task)
        return task.attempts[key]

    # ------------------------------------------------------------------ implement

    async def _step_implement(self, task: Task) -> None:
        from pathlib import Path

        owner = self.registry.get(task.owner or "") or self._agent(task.assignee_capability)
        worktree = Path(task.worktree or "")
        feedback = "\n".join(f"- {f}" for f in task.feedback[-12:])
        query = f"{task.title}\n{task.description}\n" + "\n".join(task.acceptance_criteria)
        episodic = self.memory.render(self.memory.recall(query, kind=MemoryKind.EPISODIC, agent_id=owner.id, limit=3), 1500)
        pitfalls = self.memory.render(self.memory.recall(query, kind=MemoryKind.OPERATIONAL, limit=3), 1500)
        standards = self.memory.render(self.memory.recall(query, kind=MemoryKind.PROJECT, limit=6), 2500)
        if task.track == "content":
            workspace_extra = ("You create Unreal assets with the content tools: queue every job, then call apply_content once. "
                               "Assets are created under /Game/AI_Staging and promoted to /Game/Shunya only after review and validation.")
            done = ("1. Read the brief / style documents this task depends on (under Docs/).\n"
                    "2. Queue the jobs, then apply_content must return CONTENT APPLIED with every job OK.\n"
                    "3. Submit a WorkReport listing the assets. Be honest: if a job failed and you could not fix it, set blocked.")
            output_model: type = r.WorkReport
        elif task.track == "doc":
            workspace_extra = "You write documents under Docs/ with create_doc / patch_doc." + (
                f" This task also requires a verification run (`{task.test_filter}`): run it with your tools and report its real results." if task.test_filter else "")
            done = ("1. Read the documents and code this one builds on.\n"
                    "2. Write the document(s): concrete, specific values, no filler. Other employees will act on it literally.\n"
                    "3. Submit a WorkReport. If a required verification run did not pass, say so - do not write the report as if it had.")
            output_model = r.WorkReport
        else:
            workspace_extra = f"Automation tests for this task must live under the test path prefix `{task.test_filter}`."
            done = ("1. Inspect the existing code before writing.\n"
                    "2. Implement the change and automation tests covering every acceptance criterion.\n"
                    "3. compile_project must return PASSED.\n"
                    "4. run_automation_tests with the task's test filter must return PASSED.\n"
                    "5. Submit an ImplementationReport. Be honest: set compiled/tests_passed from the actual last tool results.")
            output_model = r.ImplementationReport
        brief = _sections(
            ("Task", f"{task.id}: {task.title}\n\n{task.description}"),
            ("Acceptance criteria", "\n".join(f"{i + 1}. {c}" for i, c in enumerate(task.acceptance_criteria))),
            ("Workspace", (
                f"You are working in an isolated git worktree on branch `{task.branch}` (never `main`). Paths are relative to the Unreal project root.\n"
                f"Writable areas: {', '.join(owner.write_globs)}. Project configuration, *.Build.cs, *.Target.cs, *.uproject and Config/ are protected.\n"
                f"{workspace_extra}"
            )),
            ("Feedback you must address (from review / build / QA / humans)", feedback),
            ("Project standards and decisions", standards),
            ("Relevant knowledge (retrieved; may be incomplete - use your tools to look further)", self._knowledge(worktree, query)),
            ("Your past experience on similar work", episodic),
            ("Known build/test pitfalls in this project", pitfalls),
            ("Definition of done", done),
        )
        purpose = {"code": "implement task", "doc": "write document", "content": "create content"}.get(task.track, "implement task")
        out = await self._run_agent(
            RunRequest(agent=owner, purpose=purpose, brief=brief, output_model=output_model, control=self.controls.for_run(task.id, owner.id),
                       task=task, sandbox=self._sandbox(task, owner, writable=True), work_description=query)
        )
        if not out.ok:
            raise StepBlocked(f"{owner.name} could not finish the work: {out.run.error}")
        report = out.report  # ImplementationReport or WorkReport
        if report.blocked:  # type: ignore[union-attr]
            raise StepBlocked(f"{owner.name} reports being blocked: {report.blocked_reason}")  # type: ignore[union-attr]
        changed = await self.services.git.changed_files(worktree)
        if not changed:
            if self._bump(task, "empty") >= 2:
                raise StepBlocked("implementation produced no changes twice")
            task.feedback.append("[Orchestrator] Your last attempt changed no files. The task requires changes in the worktree.")
            self.tasks.save(task)
            return
        commit = await self.services.git.commit_all(worktree, f"{task.id}: {task.title}\n\n{report.summary}", author=owner.id)  # type: ignore[union-attr]
        diff = await self.services.git.diff(worktree)
        patch = self.services.artifacts.put(type=ArtifactType.CODE_PATCH, title=f"Diff for {task.id}", creator=owner.id, task_id=task.id,
                                            content=diff, content_type="text/x-diff", metadata={"commit": commit, "files": changed})
        task.result.update({"implementation": report.model_dump(), "commit": commit, "changed_files": changed, "patch_artifact_id": patch.id})
        task.feedback = []  # addressed; new findings will be appended by later steps
        await self.bus.publish(Event(type=EventType.ARTIFACT_CREATED, task_id=task.id, agent_id=owner.id, trace_id=task.trace_id,
                                     payload={"artifact_id": patch.id, "type": patch.type, "title": patch.title}))
        await self._idle(owner.id)
        await self.tasks.transition(task, S.REVIEW, actor=owner.id, reason=f"{len(changed)} file(s) changed, commit {str(commit)[:8]}")

    # ------------------------------------------------------------------ review

    async def _step_review(self, task: Task) -> None:
        candidates = [a for a in self.registry.with_capability(task.review_capability) if a.id != task.owner]
        if not candidates:
            raise StepBlocked(f"no independent reviewer with capability '{task.review_capability}' is available")
        reviewer = next((a for a in candidates if not self._lock(a.id).locked()), candidates[0])
        impl = task.result.get("implementation", {})
        brief = _sections(
            ("Task under review", f"{task.id}: {task.title}\n\n{task.description}"),
            ("Acceptance criteria", "\n".join(f"{i + 1}. {c}" for i, c in enumerate(task.acceptance_criteria))),
            ("Implementer's report (a claim, not evidence)", _bullets(impl)),
            ("Changed files", "\n".join(task.result.get("changed_files", []))),
            ("Your job", {
                "content": (
                    "You are the lead reviewing content before it is validated and promoted. Read the recipes under ContentJobs/ for this task "
                    "(they are exactly what was built) and the style / brief documents under Docs/ they must follow. Check every acceptance criterion: "
                    "names, colours and values against the brief, nothing missing, nothing off-brief. You cannot edit. APPROVE only if it should go into "
                    "the game; otherwise CHANGES_REQUESTED with specific findings (file = the recipe, what is wrong, what you expect). Submit a ReviewReport."
                ),
                "doc": (
                    "You are the lead reviewing this document. Read it in full (git_diff, read_file) and the documents it builds on. Check every acceptance "
                    "criterion, that values are concrete and consistent with earlier documents, and that someone could act on it without asking questions. "
                    "You cannot edit. APPROVE only if the studio should work from it; otherwise CHANGES_REQUESTED with specific findings. Submit a ReviewReport."
                ),
            }.get(task.track, (
                "You are the independent reviewer. Use git_diff and read the changed files in full. Check correctness against each acceptance "
                "criterion, Unreal conventions (UCLASS/UPROPERTY usage, replication if required, naming), edge cases, and that tests really "
                "assert the criteria. You cannot edit code. APPROVE only if you would merge it; otherwise CHANGES_REQUESTED with specific findings. "
                "Submit a ReviewReport."
            ))),
        )
        out = await self._run_agent(
            RunRequest(agent=reviewer, purpose="review diff", brief=brief, output_model=r.ReviewReport, control=self.controls.for_run(task.id, reviewer.id),
                       task=task, sandbox=self._sandbox(task, reviewer, writable=False), work_description=task.title)
        )
        if not out.ok:
            raise StepBlocked(f"review could not be completed: {out.run.error}")
        report: r.ReviewReport = out.report  # type: ignore[assignment]
        art = self.services.artifacts.put(type=ArtifactType.REVIEW_REPORT, title=f"Review of {task.id}", creator=reviewer.id, task_id=task.id,
                                          content=report.model_dump_json(indent=2), content_type="application/json")
        task.result["review"] = {**report.model_dump(), "artifact_id": art.id, "reviewer": reviewer.id}
        await self._idle(reviewer.id)
        blocking = [f for f in report.findings if f.severity in ("BLOCKER", "MAJOR")]
        if report.verdict == "APPROVE" and not blocking:
            await self.tasks.transition(task, S.BUILD, actor=reviewer.id, reason="review approved")
            return
        if self._bump(task, "review") > self.settings.max_review_rounds:
            raise StepBlocked(f"review still requests changes after {self.settings.max_review_rounds} rounds: {report.summary}")
        findings = [f"[Review {f.severity}] {f.file}:{f.line} {f.comment}" for f in report.findings] or [f"[Review] {report.summary}"]
        task.feedback.extend(findings)
        await self._message(MessageType.REVIEW_FEEDBACK, reviewer.id, task.owner or "", task, report.summary, {"findings": [f.model_dump() for f in report.findings]})
        await self.tasks.transition(task, S.CHANGES_REQUESTED, actor=reviewer.id, reason=report.summary[:200])

    # ------------------------------------------------------------------ build

    async def _step_build(self, task: Task) -> None:
        from pathlib import Path

        if task.track != "code":
            task.result["build"] = {"status": "NOT_APPLICABLE"}
            await self.tasks.transition(task, S.QA, actor="orchestrator", reason="no code changed - nothing to build")
            return
        builder = self._agent("build")
        worktree = Path(task.worktree or "")
        async with self._lock(builder.id):
            await self.statuses.set(builder.id, AgentState.COMPILING, action=f"Building {task.id}", task_id=task.id, location="server_room", trace_id=task.trace_id)
            await self.controls.for_run(task.id, builder.id).checkpoint()
            record = await self.services.run_build(project_dir=worktree, task_id=task.id, agent_id=builder.id, trace_id=task.trace_id, commit=task.result.get("commit"))
            await self._idle(builder.id)
        task.result["build"] = {"id": record.id, "status": record.status, "duration_s": record.duration_s, "log_artifact_id": record.log_artifact_id}
        if record.status in (BuildStatus.PASSED, BuildStatus.SKIPPED):
            reason = "build passed" if record.status == BuildStatus.PASSED else "build SKIPPED (no engine) - unverified"
            await self.tasks.transition(task, S.QA, actor=builder.id, reason=reason)
            return
        if record.status == BuildStatus.ERROR:
            # the build tool itself failed (environment, timeout) - engineering cannot fix that in code
            raise StepBlocked("build infrastructure error: " + "; ".join(d.message for d in record.diagnostics)[:500])
        errs = [f"[Build] {d.file}({d.line}): {d.code} {d.message}".strip() for d in record.diagnostics[:20]]
        task.feedback.extend(errs or [f"[Build] build {record.status}: {record.log_tail[-400:]}"])
        task.result["failure"] = {"stage": "build", "build_id": record.id, "errors": [d.model_dump() for d in record.diagnostics[:20]]}
        self.memory.remember(MemoryRecord(kind=MemoryKind.OPERATIONAL, task_id=task.id, title=f"Build failure on {task.id}",
                                          content="; ".join(errs)[:800] or record.log_tail[-400:], tags=["build", *[d.code for d in record.diagnostics[:5]]]))
        await self.tasks.transition(task, S.FAILED, actor=builder.id, reason=f"build {record.status}: {len(record.diagnostics)} error(s)")

    # ------------------------------------------------------------------ QA

    async def _step_qa(self, task: Task) -> None:
        if task.track == "doc":
            await self._qa_document(task)
            return
        qa = self._agent("qa")
        if qa.id == task.owner:
            raise StepBlocked("QA must be independent of the implementer")
        started = utcnow()
        unreal = self.services.content.available if task.track == "content" else not _is_unavailable(self.services.tests)
        brief = _sections(
            ("Task under test", f"{task.id}: {task.title}\n\n{task.description}"),
            ("Acceptance criteria", "\n".join(f"{i + 1}. {c}" for i, c in enumerate(task.acceptance_criteria))),
            ("Build", _bullets(task.result.get("build", {}))),
            ("Changed files", "\n".join(task.result.get("changed_files", []))),
            ("Your job", (
                "You are independent QA for content. Do not trust the author's claims. Run `validate_content` yourself: it loads every staged asset in "
                "the editor and reports facts (class, sizes, durations, level actor counts, game mode, meshes without materials). Read the recipes under "
                "ContentJobs/ and map every acceptance criterion to a fact from the validation output. If an asset is missing or invalid, or a criterion "
                "has no supporting fact, the verdict is FAIL with defects listing expected vs actual. You cannot edit. Submit a QAReport."
            ) if task.track == "content" else (
                f"You are independent QA. Do not trust the implementer's claims. Run `run_automation_tests` with filter `{task.test_filter}` yourself, "
                "read the test code to confirm each acceptance criterion is genuinely asserted (not just a test that always passes), and map every "
                "criterion to evidence (test name + what it asserts). If a criterion has no real test, or any test fails, the verdict is FAIL with "
                "defects listing expected vs actual. You cannot edit code. Submit a QAReport."
            )),
        )
        out = await self._run_agent(
            RunRequest(agent=qa, purpose="validate task", brief=brief, output_model=r.QAReport, control=self.controls.for_run(task.id, qa.id),
                       task=task, sandbox=self._sandbox(task, qa, writable=False), work_description=task.title, location="qa_lab")
        )
        if not out.ok:
            raise StepBlocked(f"QA could not be completed: {out.run.error}")
        report: r.QAReport = out.report  # type: ignore[assignment]
        runs = [t for t in self.store.tests.list(task_id=task.id, limit=200) if t.created_at >= started]
        last = runs[-1] if runs else None
        tests_status = last.status if last else "NOT_RUN"
        evidence = {
            "verdict": report.verdict,
            "criteria": [c.model_dump() for c in report.criteria],
            "defects": [d.model_dump() for d in report.defects],
            "test_run": last.model_dump(mode="json", include={"id", "status", "passed", "failed", "filter", "log_artifact_id", "commit"}) if last else None,
            "tests": [{"name": t.name, "result": t.result, "messages": t.messages} for t in (last.results if last else [])][:80],
            "build": task.result.get("build", {}).get("id"),
            "commit": task.result.get("commit"),
        }
        verdict, gate_note = report.verdict, ""
        # Evidence gate: a PASS must be backed by a passing test run made during this QA step.
        if verdict == "PASS" and unreal and tests_status != "PASSED":
            verdict, gate_note = "FAIL", f"QA claimed PASS but the test service recorded '{tests_status}' during QA; a pass requires evidence."
        if verdict == "PASS" and not all(c.met for c in report.criteria):
            verdict, gate_note = "FAIL", "QA verdict PASS contradicts its own unmet criteria."
        if verdict == "PASS" and len(report.criteria) < len(task.acceptance_criteria):
            verdict, gate_note = "FAIL", "QA did not provide evidence for every acceptance criterion."
        evidence["gate_note"] = gate_note
        evidence["tests_status"] = tests_status if unreal else "SKIPPED"
        art = self.services.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"QA report for {task.id}", creator=qa.id, task_id=task.id,
                                          content=_json({"summary": report.summary, **evidence}), content_type="application/json")
        task.result["qa"] = {"summary": report.summary, "artifact_id": art.id, "qa_agent": qa.id, **evidence}
        await self._idle(qa.id)
        if verdict == "PASS":
            if task.track == "content":
                await self._promote_content(task)
            reason = "QA passed with evidence" if unreal else "QA by static inspection only - tests were not run (no engine)"
            await self.tasks.transition(task, S.ACCEPTED, actor=qa.id, reason=reason)
            return
        task.result["failure"] = {"stage": "qa", "summary": gate_note or report.summary, "defects": evidence["defects"], "tests": [t for t in evidence["tests"] if t["result"] == "FAIL"]}
        await self.tasks.transition(task, S.FAILED, actor=qa.id, reason=(gate_note or report.summary)[:200])

    async def _promote_content(self, task: Task) -> None:
        """Reviewed and validated: move the task's assets from /Game/AI_Staging to production content (spec 40)."""
        from pathlib import Path

        worktree = Path(task.worktree or "")
        result, log = await self.services.content.run(worktree, {"mode": "promote"})
        if result.get("skipped"):
            return
        self.services.artifacts.put(type=ArtifactType.BUILD_LOG, title=f"Content promotion log for {task.id}", creator="orchestrator", content=log, task_id=task.id)
        if not result.get("ok"):
            failed = [f"{x.get('from')}: {x.get('error')}" for x in result.get("results", []) if not x.get("ok")]
            raise StepBlocked("promotion to production content failed: " + ("; ".join(failed) or str(result.get("error")))[:500])
        task.result["promoted"] = [x["path"] for x in result.get("results", [])]
        task.result["commit"] = await self.services.git.commit_all(worktree, f"{task.id}: promote reviewed content to /Game/Shunya", author=task.owner or "orchestrator")
        task.result["changed_files"] = await self.services.git.changed_files(worktree)

    async def _qa_document(self, task: Task) -> None:
        """Documents are reviewed by a lead; this step checks facts code can check, including any required verification run."""
        from pathlib import Path

        worktree = Path(task.worktree or "")
        docs = [f for f in task.result.get("changed_files", []) if f.startswith("Docs/")]
        problems: list[str] = []
        if not docs:
            problems.append("no document under Docs/ was changed")
        problems += [f"{f} is empty" for f in docs if (worktree / f).is_file() and (worktree / f).stat().st_size < 40]
        runs = self.store.tests.list(task_id=task.id, limit=200)
        last = runs[-1] if runs else None
        tests_status = "NOT_APPLICABLE"
        if task.test_filter:
            available = not _is_unavailable(self.services.tests)
            tests_status = (last.status if last else "NOT_RUN") if available else "SKIPPED"
            if available and tests_status != "PASSED":
                problems.append(f"this task requires a passing verification run ('{task.test_filter}'); the latest recorded run is {tests_status}")
        review = task.result.get("review", {})
        images = [a.id for a in self.store.artifacts.list(task_id=task.id) if a.content_type == "image/png"]
        evidence = {
            "verdict": "FAIL" if problems else "PASS",
            "criteria": [{"criterion": c, "met": not problems, "evidence": f"reviewed by {review.get('reviewer')}: {review.get('summary', '')}"[:300]} for c in task.acceptance_criteria],
            "defects": [{"title": p, "severity": "HIGH", "test": task.test_filter, "expected": "", "actual": p} for p in problems],
            "test_run": last.model_dump(mode="json", include={"id", "status", "passed", "failed", "filter", "log_artifact_id"}) if last else None,
            "tests": [{"name": t.name, "result": t.result, "messages": t.messages} for t in (last.results if last else [])][:80],
            "tests_status": tests_status, "gate_note": "; ".join(problems), "images": images,
            "qa_agent": "orchestrator", "summary": "Document checks passed." if not problems else "; ".join(problems),
        }
        task.result["qa"] = evidence
        if not problems:
            await self.tasks.transition(task, S.ACCEPTED, actor="orchestrator", reason="document reviewed; checks passed")
            return
        task.result["failure"] = {"stage": "qa", "summary": "; ".join(problems), "defects": evidence["defects"], "tests": [t for t in evidence["tests"] if t["result"] == "FAIL"]}
        await self.tasks.transition(task, S.FAILED, actor="orchestrator", reason="; ".join(problems)[:200])

    # ------------------------------------------------------------------ failure -> bug -> engineering

    async def _step_failed(self, task: Task) -> None:
        failure = task.result.get("failure", {})
        stage = failure.get("stage", "unknown")
        limit = self.settings.max_build_attempts if stage == "build" else self.settings.max_qa_rounds
        if self._bump(task, f"fix_{stage}") > limit:
            raise StepBlocked(f"{stage} still failing after {limit} fix attempts: {failure.get('summary') or failure.get('errors', '')}"[:600])
        reporter = (task.result.get("qa", {}).get("qa_agent") if stage == "qa" else self._agent("build").id) or "orchestrator"
        if stage == "qa":
            defects = failure.get("defects") or [{"title": failure.get("summary", "QA failed"), "severity": "HIGH", "test": "", "expected": "", "actual": ""}]
            for d in defects:
                bug = Bug(task_id=task.id, title=d["title"], severity=Severity(d.get("severity", "HIGH")), reporter=reporter, evidence={**d, "failed_tests": failure.get("tests", [])})
                self.store.bugs.put(bug)
                task.feedback.append(f"[QA {bug.id}] {d['title']} - test: {d.get('test')}; expected: {d.get('expected')}; actual: {d.get('actual')}")
                await self.bus.publish(Event(type=EventType.BUG_CREATED, task_id=task.id, agent_id=reporter, trace_id=task.trace_id,
                                             payload={"bug_id": bug.id, "title": bug.title, "severity": bug.severity}))
            for t in failure.get("tests", [])[:10]:
                task.feedback.append(f"[QA failing test] {t['name']}: {'; '.join(t.get('messages', []))}")
            if failure.get("summary"):
                task.feedback.append(f"[QA] {failure['summary']}")
            await self._message(MessageType.BUG_REPORT, reporter, task.owner or "", task, failure.get("summary", "QA failed"), failure, Severity.HIGH)
        else:
            bug = Bug(task_id=task.id, title=f"Build broken on {task.id}", severity=Severity.HIGH, reporter=reporter, evidence=failure)
            self.store.bugs.put(bug)
            await self.bus.publish(Event(type=EventType.BUG_CREATED, task_id=task.id, agent_id=reporter, trace_id=task.trace_id,
                                         payload={"bug_id": bug.id, "title": bug.title, "severity": bug.severity}))
            await self._message(MessageType.BUILD_FAILURE, reporter, task.owner or "", task, f"Official build failed with {len(failure.get('errors', []))} error(s)", failure, Severity.HIGH)
        await self.tasks.transition(task, S.BUG_CREATED, actor=reporter, reason=f"{stage} failure handed back to engineering")

    # ------------------------------------------------------------------ approval + merge

    async def _step_request_approval(self, task: Task) -> None:
        from pathlib import Path

        worktree = Path(task.worktree or "")
        diff = await self.services.git.diff(worktree)
        changed = await self.services.git.changed_files(worktree)
        build_status = str(task.result.get("build", {}).get("status", "NOT_RUN"))
        tests_status = str(task.result.get("qa", {}).get("tests_status", "NOT_RUN"))
        risk, reasons = assess_risk(changed_files=changed, diff=diff, build_status=build_status, tests_status=tests_status)
        if task.test_filter == "package":
            # spec 28: packaging / release always goes to the studio owner, whatever the diff looks like
            risk, reasons = RiskLevel.HIGH, ["release packaging: the studio owner signs off every packaged build", *reasons]
        patch = self.services.artifacts.put(type=ArtifactType.CODE_PATCH, title=f"Diff for {task.id}", creator=task.owner or "orchestrator", task_id=task.id,
                                            content=diff, content_type="text/x-diff", metadata={"commit": task.result.get("commit"), "files": changed}, status="PENDING_APPROVAL")
        approval = Approval(
            task_id=task.id, agent_id=task.owner or "orchestrator", requested_action=f"Merge {task.branch} into develop",
            risk_level=risk, risk_reasons=reasons, diff_artifact_id=patch.id,
            reason=str(task.result.get("implementation", {}).get("summary", ""))[:1200],
            evidence={
                "changed_files": changed, "commit": task.result.get("commit"),
                "build": task.result.get("build"), "review": task.result.get("review"), "qa": task.result.get("qa"), "track": task.track,
                "images": [a.id for a in self.store.artifacts.list(task_id=task.id) if a.content_type == "image/png"],
                "acceptance_criteria": task.acceptance_criteria, "cost_usd": task.cost_usd, "llm_calls": task.llm_calls,
            },
        )
        task.result["approval_id"] = approval.id
        await self.tasks.transition(task, S.AWAITING_APPROVAL, actor="orchestrator", reason=f"risk {risk}")
        await self.approvals.request(approval)
        if self.approval_policy_allows(risk):
            await self.approvals.decide(approval.id, granted=True, decided_by="policy", comment=f"approved by policy: computed risk {risk} is within the auto-approve limit")
        elif task.owner:
            await self.statuses.set(task.owner, AgentState.WAITING_APPROVAL, action=f"Waiting for approval of {task.id}", task_id=task.id)

    def approval_policy_allows(self, risk) -> bool:
        """The studio owner may delegate low-risk merges to policy; everything else waits for them."""
        order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        limit = (self.settings.auto_approve_max_risk or "").upper()
        return limit in order and order.index(str(risk)) <= order.index(limit)

    async def _step_await_approval(self, task: Task) -> None:
        approval_id = task.result.get("approval_id")
        approval = self.store.approvals.get(approval_id) if approval_id else None
        if approval is None:
            await self.tasks.transition(task, S.BLOCKED, actor="orchestrator", reason="approval record missing")
            return
        waiter = asyncio.create_task(self.approvals.wait(approval.id))
        control = self.controls.task(task.id)
        try:
            while not waiter.done():
                if control.cancelled:
                    raise RunCancelled()
                await asyncio.wait([waiter], timeout=0.5)
            approval = waiter.result()
        finally:
            waiter.cancel()
        if approval.status == ApprovalStatus.GRANTED:
            merge = await self.services.git.merge_to_develop(task.id, f"Merge {task.branch}: {task.title} (approved by {approval.decided_by}, {approval.id})")
            task.result["merge_commit"] = merge
            await self.services.git.remove_worktree(task.id)
            for bug in self.store.bugs.list(task_id=task.id, status="OPEN"):
                bug.status = "CLOSED"
                self.store.bugs.put(bug)
            await self._idle(task.owner)
            self.memory.remember(MemoryRecord(kind=MemoryKind.EPISODIC, agent_id=task.owner, task_id=task.id, title=f"Delivered {task.id}: {task.title}",
                                              content=str(task.result.get("implementation", {}).get("summary", ""))[:800], tags=["delivered", *task.result.get("changed_files", [])[:8]]))
            await self.tasks.transition(task, S.DONE, actor=approval.decided_by or "user", reason=f"approved and merged to develop ({merge[:8]})")
        else:
            await self.tasks.transition(task, S.REJECTED, actor=approval.decided_by or "user", reason=approval.comment or "rejected")
            await self._idle(task.owner)
            if approval.rework_requested:
                task.feedback.append(f"[Human rejection] {approval.comment or 'Changes requested by the studio owner.'}")
                task.attempts = {}
                self.tasks.save(task)
            else:
                task.result["rejected"] = approval.comment
                await self._cancel_cleanup(task)


# ---------------------------------------------------------------------- helpers


def _sections(*sections: tuple[str, str]) -> str:
    return "\n\n".join(f"## {title}\n{body.strip()}" for title, body in sections if body and body.strip())


def _bullets(d: dict[str, Any]) -> str:
    out = []
    for k, v in d.items():
        if isinstance(v, list):
            v = "; ".join(str(x) for x in v) or "-"
        out.append(f"- {k}: {v}")
    return "\n".join(out)


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)


def _is_unavailable(service: Any) -> bool:
    from shunya.tools.unreal_build import UnavailableTestService

    return isinstance(service, UnavailableTestService)
