"""Shared services handed to tools through ToolContext.

Build and test execution is recorded here (BuildRecord / TestRunRecord, log artifacts,
BUILD_* / TEST_* events) so a compile triggered by a programmer's tool call and the
Build Engineer's official build leave the same evidence trail.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from shunya.config import Settings
from shunya.core.artifacts import FileArtifactStore
from shunya.core.interfaces import IEventBus, IUnrealBridge
from shunya.core.persistence import Store
from shunya.knowledge import HybridRetriever
from shunya.shared.schemas import ArtifactType, BuildRecord, BuildStatus, Event, EventType, TestRunRecord
from shunya.tools.git_tools import GitService
from shunya.tools.base import ToolError
from shunya.tools.unreal_build import IBuildService, ITestService, UnavailableBuildService
from shunya.tools.unreal_content import IContentService, IPlaytestService, copy_binaries, is_built, mark_built, source_fingerprint


@dataclass
class ToolServices:
    settings: Settings
    store: Store
    bus: IEventBus
    artifacts: FileArtifactStore
    git: GitService
    build: IBuildService
    tests: ITestService
    bridge: IUnrealBridge
    content: IContentService
    playtest: IPlaytestService
    studio_docs: list[Path] = field(default_factory=list)
    _retrievers: dict[str, tuple[float, HybridRetriever]] = field(default_factory=dict)
    _develop_build: asyncio.Lock = field(default_factory=asyncio.Lock)

    def retriever_for(self, root: Path) -> HybridRetriever:
        """Index of one working copy, rebuilt when its sources change."""
        key = str(root.resolve())
        stamp = _tree_stamp(root)
        cached = self._retrievers.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        retriever = HybridRetriever().ingest(root, extra_docs=self.studio_docs)
        self._retrievers[key] = (stamp, retriever)
        return retriever

    async def run_build(self, *, project_dir: Path, task_id: str | None, agent_id: str, trace_id: str | None, commit: str | None = None) -> BuildRecord:
        await self.bus.publish(Event(type=EventType.BUILD_STARTED, task_id=task_id, agent_id=agent_id, trace_id=trace_id))
        record, log = await self.build.compile(project_dir)
        record.task_id, record.agent_id, record.commit = task_id, agent_id, commit
        art = self.artifacts.put(type=ArtifactType.BUILD_LOG, title=f"Build log {record.id}", creator=agent_id, content=log, task_id=task_id)
        record.log_artifact_id = art.id
        self.store.builds.put(record)
        if record.status == BuildStatus.PASSED:
            mark_built(project_dir)
        etype = EventType.BUILD_PASSED if record.status == BuildStatus.PASSED else EventType.BUILD_FAILED
        await self.bus.publish(
            Event(
                type=etype, task_id=task_id, agent_id=agent_id, trace_id=trace_id,
                payload={"build_id": record.id, "status": record.status, "errors": len(record.diagnostics), "duration_s": record.duration_s},
            )
        )
        return record

    async def run_tests(self, *, project_dir: Path, test_filter: str, task_id: str | None, agent_id: str, trace_id: str | None, commit: str | None = None, build_id: str | None = None) -> TestRunRecord:
        await self.ensure_built(project_dir, task_id=task_id, agent_id=agent_id, trace_id=trace_id)
        await self.bus.publish(Event(type=EventType.TEST_STARTED, task_id=task_id, agent_id=agent_id, trace_id=trace_id, payload={"filter": test_filter}))
        record, log = await self.tests.run_tests(project_dir, test_filter)
        record.task_id, record.commit, record.build_id = task_id, commit, build_id
        art = self.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"Test log {record.id}", creator=agent_id, content=log, task_id=task_id)
        record.log_artifact_id = art.id
        return await self.record_test_run(record, agent_id=agent_id, trace_id=trace_id, announce_start=False)

    async def record_test_run(self, record: TestRunRecord, *, agent_id: str, trace_id: str | None, announce_start: bool = True) -> TestRunRecord:
        """Persist any kind of verification run (automation tests, content validation, playtest) as evidence."""
        if announce_start:
            await self.bus.publish(Event(type=EventType.TEST_STARTED, task_id=record.task_id, agent_id=agent_id, trace_id=trace_id, payload={"filter": record.filter}))
        self.store.tests.put(record)
        etype = EventType.TEST_PASSED if record.status == "PASSED" else EventType.TEST_FAILED
        await self.bus.publish(
            Event(
                type=etype, task_id=record.task_id, agent_id=agent_id, trace_id=trace_id,
                payload={"test_run_id": record.id, "status": record.status, "passed": record.passed, "failed": record.failed, "filter": record.filter},
            )
        )
        return record

    async def ensure_built(self, project_dir: Path, *, task_id: str | None, agent_id: str, trace_id: str | None) -> None:
        """Make sure a working copy has editor binaries matching its sources before the editor is launched on it.

        A worktree whose code is identical to the develop checkout reuses its binaries instead
        of compiling again; only worktrees with code changes are compiled themselves.
        """
        if isinstance(self.build, UnavailableBuildService) or is_built(project_dir):
            return
        main = self.settings.game_repo
        if project_dir.resolve() != main.resolve() and main.is_dir() and source_fingerprint(main) == source_fingerprint(project_dir):
            async with self._develop_build:  # several waiting tasks must trigger one develop build, not one each
                if not is_built(main):
                    rec = await self.run_build(project_dir=main, task_id=task_id, agent_id="build_engineer_01", trace_id=trace_id)
                    if rec.status != BuildStatus.PASSED:
                        raise ToolError("the develop branch does not compile: " + "; ".join(d.message for d in rec.diagnostics[:5]))
            copy_binaries(main, project_dir)
            mark_built(project_dir)
            return
        rec = await self.run_build(project_dir=project_dir, task_id=task_id, agent_id=agent_id, trace_id=trace_id)
        if rec.status != BuildStatus.PASSED:
            raise ToolError("the project does not compile: " + "; ".join(d.message for d in rec.diagnostics[:5]))


def _tree_stamp(root: Path) -> float:
    latest = 0.0
    for top in ("Source", "Plugins", "Docs"):
        base = root / top
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "Intermediate" not in p.parts and "Binaries" not in p.parts:
                latest = max(latest, p.stat().st_mtime)
    return latest
