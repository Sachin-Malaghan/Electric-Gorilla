"""Composition root: wires the modular monolith together (spec 3, 45, 46).

Everything is constructed here from Settings and handed its dependencies explicitly, so
tests can swap any piece (provider, build service, bus) through the keyword arguments.
"""

from __future__ import annotations

import logging
from typing import Any

from shunya.bridge import HttpUnrealBridge
from shunya.config import Settings, load_settings
from shunya.core import processes
from shunya.core.models.pricing import CUSTOM_PRICES, PRICES, set_custom_price
from shunya.core.secrets import KEY_NAME, LLM_KEY_NAME, LLM_MODEL_NAME, LLM_URL_NAME, SecretStore, SpendMeter, hint
from shunya.core.agent_runtime import AgentRegistry, AgentRunner, AgentStatusService, ControlRegistry, PromptComposer
from shunya.core.artifacts import FileArtifactStore
from shunya.core.games import GamePublisher, GameRegistry
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
from shunya.tools.unreal_content import (
    IContentService,
    IPackageService,
    IPlaytestService,
    UnavailablePackageService,
    UnrealPackageService,
    UnavailableContentService,
    UnavailablePlaytestService,
    UnrealContentService,
    UnrealPlaytestService,
)
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
        content: IContentService | None = None,
        playtest: IPlaytestService | None = None,
        packager: IPackageService | None = None,
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
        self.games = GameRegistry(s, self.store)
        self.publisher = GamePublisher(s, self.games)
        # worktree-level operations (diff, commit) are the same for every game; repository-level ones go through self.games.git(id)
        self.git = GitService(s.games_dir, s.worktrees_dir)
        if build is None:
            build = UnrealBuildService(s.engine_root, s.game_project_name, s.build_timeout_s) if s.unreal_available else UnavailableBuildService()
        if tests is None:
            tests = (
                UnrealTestService(s.engine_root, s.game_project_name, s.data_dir / "test_runs", s.test_timeout_s)
                if s.unreal_available
                else UnavailableTestService()
            )
        self.bridge = bridge or HttpUnrealBridge(s.bridge_url, s.bridge_token)
        if content is None:
            content = UnrealContentService(s.engine_root, s.game_project_name) if s.unreal_available else UnavailableContentService()
        if playtest is None:
            playtest = UnrealPlaytestService(s.engine_root, s.game_project_name) if s.unreal_available else UnavailablePlaytestService()
        if packager is None:
            packager = UnrealPackageService(s.engine_root, s.game_project_name, s.package_timeout_s) if s.unreal_available else UnavailablePackageService()
        self.services = ToolServices(
            settings=s, store=self.store, bus=self.bus, artifacts=self.artifacts, git=self.git, build=build, tests=tests,
            bridge=self.bridge, content=content, playtest=playtest, packager=packager, games=self.games,
        )
        self.permissions = PermissionEngine()
        self.tools = build_registry(self.permissions)
        self.secrets = SecretStore(s.data_dir)
        self.spend = SpendMeter(self.store, s.max_spend_usd)
        if provider is None:
            s.llm_base_url = s.llm_base_url or self.secrets.get(LLM_URL_NAME)
            if not s.provider_pinned:  # a key was supplied and nothing says otherwise: use it
                if self.secrets.llm_key()[0] and s.llm_base_url:
                    s.model_provider = "openai"
                elif self.secrets.anthropic_key()[0]:
                    s.model_provider = "anthropic"
            self._apply_endpoint_models(self.secrets.get(LLM_MODEL_NAME))
            provider = create_provider(s, api_key=self.secrets.key_for(s.model_provider)[0] or None)
        self.provider = provider
        self.router = ModelRouter(s)
        self.memory = MemoryService(self.store)
        self.controls = ControlRegistry()
        self.approvals = ApprovalService(self.store, self.bus)
        self.runner = AgentRunner(
            provider=self.provider, router=self.router, registry=self.tools, services=self.services, store=self.store, bus=self.bus,
            statuses=self.statuses, composer=PromptComposer(s.prompts_dir), tasks=self.tasks, memory=self.memory, spend=self.spend,
        )
        self.orchestrator = Orchestrator(
            settings=s, store=self.store, bus=self.bus, tasks=self.tasks, registry=self.registry, statuses=self.statuses,
            runner=self.runner, services=self.services, approvals=self.approvals, memory=self.memory, controls=self.controls,
            games=self.games, publisher=self.publisher,
        )
        self._started = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> "Studio":
        if self._started:
            return self
        s = self.settings
        if isinstance(self.bus, RedisEventBus):
            await self.bus.start()
        s.games_dir.mkdir(parents=True, exist_ok=True)
        for game in self.games.adopt_existing():
            log.info("adopted existing game folder %s", game.repo_path)
        self.store.projects.put(Project(id="shunya", name="Shunya", repo_path=str(s.games_dir), engine_root=str(s.engine_root) if s.engine_root else None,
                                        description="The games the studio is developing, one folder each"))
        await self.statuses.bootstrap()
        await self.orchestrator.recover()
        self._started = True
        return self

    async def stop(self) -> None:
        await self.orchestrator.shutdown()
        killed = processes.kill_all()  # no compiler or editor may outlive the studio
        if killed:
            log.warning("terminated %d child process tree(s) on shutdown", killed)
        self.store.close()
        self._started = False

    # ------------------------------------------------------------------ model settings (owner only)

    def _apply_endpoint_models(self, model: str) -> None:
        """An endpoint model chosen in the office applies to every tier unless SHUNYA_MODEL_* say otherwise."""
        s = self.settings
        if s.model_provider == "openai" and model and not s.models_pinned:
            s.model_fast = s.model_standard = s.model_strong = model
        set_custom_price([s.model_fast, s.model_standard, s.model_strong], s.model_price_input, s.model_price_output)

    def model_settings(self) -> dict[str, Any]:
        provider = self.settings.model_provider
        key, source = self.secrets.key_for(provider)
        any_key = bool(self.secrets.anthropic_key()[0] or self.secrets.llm_key()[0])
        return {
            "provider": provider, "key_set": bool(key), "any_key_set": any_key, "key_hint": hint(key), "key_source": source,
            "base_url": self.settings.llm_base_url if provider == "openai" else "",
            "price_known": all(m in PRICES or m in CUSTOM_PRICES for m in (self.settings.model_standard,)) or provider == "scripted",
            "models": {"fast": self.settings.model_fast, "standard": self.settings.model_standard, "strong": self.settings.model_strong},
            "spent_usd": self.spend.spent_usd, "max_spend_usd": self.spend.limit_usd, "remaining_usd": self.spend.remaining_usd,
        }

    def configure_model(self, *, provider: str | None = None, api_key: str | None = None, max_spend_usd: float | None = None,
                        base_url: str | None = None, model: str | None = None) -> dict[str, Any]:
        """Switch provider / key / endpoint / cap while running. New agent runs use the new provider; runs in flight finish on the old one."""
        s = self.settings
        target = provider or ("openai" if base_url else s.model_provider if s.model_provider != "scripted" else "anthropic" if api_key else "scripted")
        if api_key is not None:
            if target == "scripted":  # removing: clear whatever was stored
                self.secrets.set(KEY_NAME, "")
                self.secrets.set(LLM_KEY_NAME, "")
            else:
                self.secrets.set(LLM_KEY_NAME if target == "openai" else KEY_NAME, api_key.strip())
        if base_url is not None:
            self.secrets.set(LLM_URL_NAME, base_url.strip())
            s.llm_base_url = base_url.strip()
        if model is not None:
            self.secrets.set(LLM_MODEL_NAME, model.strip())
        if max_spend_usd is not None:
            s.max_spend_usd = self.spend.limit_usd = max_spend_usd
        if any(v is not None for v in (provider, api_key, base_url, model)):
            key, _ = self.secrets.key_for(target)
            if target != "scripted" and not key:
                raise ValueError("an API key is needed before the studio can use real agents")
            if target == "openai" and not s.llm_base_url:
                raise ValueError("an endpoint URL is needed for an OpenAI-compatible provider")
            if target == "openai" and not (self.secrets.get(LLM_MODEL_NAME) or s.models_pinned):
                raise ValueError("a model name is needed for an OpenAI-compatible provider")
            s.model_provider = target
            self._apply_endpoint_models(self.secrets.get(LLM_MODEL_NAME))
            self.provider = self.runner.provider = create_provider(s, api_key=key or None)
        return self.model_settings()

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
            "auto_approve_max_risk": self.settings.auto_approve_max_risk,
            "games": [g.model_dump(mode="json") for g in self.games.all()],
            "spend": {"spent_usd": self.spend.spent_usd, "max_spend_usd": self.spend.limit_usd},
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

