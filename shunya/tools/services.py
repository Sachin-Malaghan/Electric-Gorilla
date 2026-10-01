"""Shared services handed to tools through ToolContext.

Build and test execution is recorded here (BuildRecord / TestRunRecord, log artifacts,
BUILD_* / TEST_* events) so a compile triggered by a programmer's tool call and the
Build Engineer's official build leave the same evidence trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from shunya.config import Settings
from shunya.core.artifacts import FileArtifactStore
from shunya.core.interfaces import IEventBus, IUnrealBridge
from shunya.core.persistence import Store
from shunya.knowledge import HybridRetriever
from shunya.shared.schemas import ArtifactType, BuildRecord, BuildStatus, Event, EventType, TestRunRecord
from shunya.tools.git_tools import GitService
from shunya.tools.unreal_build import IBuildService, ITestService


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
    studio_docs: list[Path] = field(default_factory=list)
    _retrievers: dict[str, tuple[float, HybridRetriever]] = field(default_factory=dict)

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
        etype = EventType.BUILD_PASSED if record.status == BuildStatus.PASSED else EventType.BUILD_FAILED
        await self.bus.publish(
            Event(
                type=etype, task_id=task_id, agent_id=agent_id, trace_id=trace_id,
                payload={"build_id": record.id, "status": record.status, "errors": len(record.diagnostics), "duration_s": record.duration_s},
            )
        )
        return record

    async def run_tests(self, *, project_dir: Path, test_filter: str, task_id: str | None, agent_id: str, trace_id: str | None, commit: str | None = None, build_id: str | None = None) -> TestRunRecord:
        await self.bus.publish(Event(type=EventType.TEST_STARTED, task_id=task_id, agent_id=agent_id, trace_id=trace_id, payload={"filter": test_filter}))
        record, log = await self.tests.run_tests(project_dir, test_filter)
        record.task_id, record.commit, record.build_id = task_id, commit, build_id
        art = self.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"Test log {record.id}", creator=agent_id, content=log, task_id=task_id)
        record.log_artifact_id = art.id
        self.store.tests.put(record)
        etype = EventType.TEST_PASSED if record.status == "PASSED" else EventType.TEST_FAILED
        await self.bus.publish(
            Event(
                type=etype, task_id=task_id, agent_id=agent_id, trace_id=trace_id,
                payload={"test_run_id": record.id, "status": record.status, "passed": record.passed, "failed": record.failed, "filter": test_filter},
            )
        )
        return record


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
