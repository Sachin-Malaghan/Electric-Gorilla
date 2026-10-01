"""Composition root: wires the modular monolith together (spec 3, 45, 46).

Everything is constructed here from Settings and handed its dependencies explicitly, so
tests can swap any piece (provider, build service, bus) through the keyword arguments.
"""

from __future__ import annotations

import logging
from typing import Any

from shunya.bridge import HttpUnrealBridge
from shunya.config import Settings, load_settings
from shunya.core.agent_runtime import AgentRegistry, AgentRunner, AgentStatusService, ControlRegistry, PromptComposer
from shunya.core.artifacts import FileArtifactStore
from shunya.core.events import InMemoryEventBus, RedisEventBus
from shunya.core.interfaces import IEventBus, IModelProvider, IUnrealBridge
from shunya.core.memory import MemoryService
from shunya.core.models import ModelRouter, create_provider
from shunya.core.orchestration.approvals import ApprovalService
from shunya.core.orchestration.workflow import Orchestrator
from shunya.core.permissions import PermissionEngine
from shunya.core.persistence import Store
from shunya.core.task_engine import SqlTaskRepository, TaskService
from shunya.shared.schemas import (
    AgentState,
    ApprovalStatus,
    MemoryKind,
    MemoryRecord,
    Project,
    TaskStatus,
    TaskType,
)
from shunya.tools.git_tools import GitService
from shunya.tools.registry import build_registry
from shunya.tools.services import ToolServices
from shunya.tools.unreal_build import (
    IBuildService,
    ITestService,
    UnavailableBuildService,
    UnavailableTestService,
    UnrealBuildService,
    UnrealTestService,
)

log = logging.getLogger(__name__)


class Studio:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        provider: IModelProvider | None = None,
        build: IBuildService | None = None,
        tests: ITestService | None = None,
        bus: IEventBus | None = None,
        bridge: IUnrealBridge | None = None,
    ):
        self.settings = settings or load_settings()
        s = self.settings
        s.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(s.db_url)
        if bus is not None:
            self.bus = bus
        elif s.redis_url:
            self.bus = RedisEventBus(s.redis_url, self.store.events)
        else:
            self.bus = InMemoryEventBus(self.store.events)
        self.tasks = TaskService(SqlTaskRepository(self.store), self.bus)
        self.registry = AgentRegistry(s.agents_dir).load()
        self.statuses = AgentStatusService(self.store, self.bus, self.registry)
        self.artifacts = FileArtifactStore(s.artifacts_dir, self.store)
        self.git = GitService(s.game_repo, s.worktrees_dir)
        if build is None:
            build = UnrealBuildService(s.engine_root, s.game_project_name, s.build_timeout_s) if s.unreal_available else UnavailableBuildService()
        if tests is None:
            tests = (
                UnrealTestService(s.engine_root, s.game_project_name, s.data_dir / "test_runs", s.test_timeout_s)
                if s.unreal_available
                else UnavailableTestService()
            )
        self.bridge = bridge or HttpUnrealBridge(s.bridge_url, s.bridge_token)
        self.services = ToolServices(
            settings=s, store=self.store, bus=self.bus, artifacts=self.artifacts, git=self.git, build=build, tests=tests,
            bridge=self.bridge,
        )
        self.permissions = PermissionEngine()
        self.tools = build_registry(self.permissions)
        self.provider = provider or create_provider(s)
        self.router = ModelRouter(s)
        self.memory = MemoryService(self.store)
        self.controls = ControlRegistry()
        self.approvals = ApprovalService(self.store, self.bus)
        self.runner = AgentRunner(
            provider=self.provider, router=self.router, registry=self.tools, services=self.services, store=self.store, bus=self.bus,
            statuses=self.statuses, composer=PromptComposer(s.prompts_dir), tasks=self.tasks, memory=self.memory,
        )
        self.orchestrator = Orchestrator(
            settings=s, store=self.store, bus=self.bus, tasks=self.tasks, registry=self.registry, statuses=self.statuses,
            runner=self.runner, services=self.services, approvals=self.approvals, memory=self.memory, controls=self.controls,
        )
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> "Studio":
        if self._started:
            return self
        s = self.settings
        if isinstance(self.bus, RedisEventBus):
            await self.bus.start()
        await self.git.ensure_repo(s.game_template)
        self.store.projects.put(Project(id="shunya", name="Shunya", repo_path=str(s.game_repo), engine_root=str(s.engine_root) if s.engine_root else None,
                                        description="The Unreal game the studio is developing"))
        self._seed_project_memory()
        await self.statuses.bootstrap()
        await self.orchestrator.recover()
        self._started = True
        return self

    async def stop(self) -> None:
        await self.orchestrator.shutdown()
        self.store.close()
        self._started = False

    def _seed_project_memory(self) -> None:
        """Project memory = the decisions and standards agents must retrieve before acting (spec 37)."""
        existing = {m.title for m in self.store.memories.list(limit=5000) if m.kind == MemoryKind.PROJECT}
        docs = self.settings.game_repo / "Docs"
        for path in sorted([*docs.glob("adr/*.md"), *docs.glob("CodingStandards.md")]):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
            if title not in existing:
                self.memory.remember(MemoryRecord(kind=MemoryKind.PROJECT, title=title, content=text[:1500], tags=["adr", path.stem]))

    # ------------------------------------------------------------------ read model for the 2.5D studio

    def agent_view(self, agent_id: str) -> dict[str, Any] | None:
        profile = self.registry.get(agent_id)
        if profile is None:
            return None
        status = self.statuses.get(agent_id)
        run = self.store.runs.get(status.run_id) if status.run_id else None
        return {
            "id": profile.id, "name": profile.name, "role": profile.role, "department": profile.department,
            "enabled": profile.enabled, "capability": profile.capability, "supervisor": profile.supervisor,
            "avatar": profile.avatar.model_dump(),
            "state": status.state if profile.enabled else AgentState.OFFLINE,
            "task_id": status.task_id, "run_id": status.run_id, "current_action": status.current_action,
            "location": status.location, "paused": status.paused, "since": status.since.isoformat(),
            "run": run.model_dump(mode="json", include={"id", "model", "iterations", "tool_calls", "llm_calls", "input_tokens", "output_tokens", "cost_usd", "files_inspected", "files_modified", "phase", "status", "purpose", "started_at"}) if run else None,
        }

    def snapshot(self) -> dict[str, Any]:
        tasks = self.store.tasks.list(limit=2000)
        features = [t for t in tasks if t.type in (TaskType.FEATURE, TaskType.EPIC)]
        work = [t for t in tasks if t.type not in (TaskType.FEATURE, TaskType.EPIC)]
        agents = [self.agent_view(p.id) for p in self.registry.all()]
        enabled = [a for a in agents if a and a["enabled"]]
        builds = self.store.builds.list(limit=1, newest_first=True)
        tests = self.store.tests.list(limit=1, newest_first=True)
        bugs = self.store.bugs.list(status="OPEN", limit=1000)
        current = next((f for f in reversed(features) if f.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)), features[-1] if features else None)
        epic = None
        if current:
            kids = [t for t in work if t.parent_id == current.id]
            done = sum(1 for k in kids if k.status == TaskStatus.DONE)
            epic = {"id": current.id, "title": current.title, "status": current.status, "tasks": len(kids), "done": done,
                    "progress": round(100 * done / len(kids)) if kids else 0}
        working = {AgentState.IDLE, AgentState.OFFLINE, AgentState.MEETING, AgentState.TESTING, AgentState.BLOCKED, AgentState.SUCCESS, AgentState.FAILED, AgentState.WAITING_APPROVAL}
        return {
            "studio": "SHUNYA STUDIOS",
            "project": self.store.projects.get("shunya").model_dump() if self.store.projects.get("shunya") else None,
            "provider": self.settings.model_provider,
            "unreal_available": self.settings.unreal_available,
            "last_seq": self.store.events.last_seq(),
            "agents": agents,
            "tasks": [t.model_dump(mode="json", exclude={"history"}) for t in tasks],
            "approvals": [a.model_dump(mode="json") for a in self.store.approvals.list(status=str(ApprovalStatus.PENDING), newest_first=True)],
            "meetings": [m.model_dump(mode="json") for m in self.store.meetings.list(status="OPEN")],
            "epic": epic,
            "stats": {
                "agents": len(enabled),
                "working": sum(1 for a in enabled if a["state"] not in working),
                "meeting": sum(1 for a in enabled if a["state"] == AgentState.MEETING),
                "testing": sum(1 for a in enabled if a["state"] == AgentState.TESTING),
                "blocked": sum(1 for a in enabled if a["state"] in (AgentState.BLOCKED, AgentState.FAILED)),
                "build": builds[0].status if builds else None,
                "tests": {"passed": tests[0].passed, "total": tests[0].passed + tests[0].failed, "status": tests[0].status} if tests else None,
                "open_bugs": len(bugs),
                "critical_bugs": sum(1 for b in bugs if b.severity == "CRITICAL"),
                "cost_usd": round(sum(t.cost_usd for t in tasks), 4),
            },
        }

