from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shunya.config import load_settings
from shunya.core.models.demo_scripts import demo_scripts
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.shared.schemas import (
    ApprovalStatus,
    BuildRecord,
    BuildStatus,
    CompileDiagnostic,
    TaskStatus,
    TestCaseResult,
    TestRunRecord,
)
from shunya.studio import Studio
from shunya.tools.unreal_build import IBuildService, ITestService

HEALTH_TESTS = [
    "ShunyaGame.Health.DefaultsTo100",
    "ShunyaGame.Health.DamageCannotGoBelowZero",
    "ShunyaGame.Health.DeathEventFiresOnce",
    "ShunyaGame.Health.HealClampsToMax",
    "ShunyaGame.Health.ReplicatedForMultiplayer",
]


class FakeBuildService(IBuildService):
    """Stands in for UnrealBuildTool: 'compiles' by looking for the demo's known typo."""

    def __init__(self) -> None:
        self.calls = 0
        self.always_fail = False

    async def compile(self, project_dir: Path):
        self.calls += 1
        src = project_dir / "Source/ShunyaGame/Private/Components/HealthComponent.cpp"
        text = src.read_text(encoding="utf-8") if src.is_file() else ""
        if self.always_fail or "MaxHeath)" in text:
            diag = CompileDiagnostic(
                file="Source/ShunyaGame/Private/Components/HealthComponent.cpp", line=58, code="C2065",
                message="'MaxHeath': undeclared identifier",
            )
            log = f"{src}(58): error C2065: 'MaxHeath': undeclared identifier\nResult: Failed"
            return BuildRecord(status=BuildStatus.FAILED, target="ShunyaGameEditor", diagnostics=[diag], log_tail=log), log
        return BuildRecord(status=BuildStatus.PASSED, target="ShunyaGameEditor", duration_s=0.1), "Result: Succeeded"


class FakeTestService(ITestService):
    def __init__(self) -> None:
        self.calls = 0
        self.failing: set[str] = set()

    async def run_tests(self, project_dir: Path, test_filter: str):
        self.calls += 1
        tests = project_dir / "Source/ShunyaGame/Private/Tests/HealthComponentTests.cpp"
        if not tests.is_file():
            rec = TestRunRecord(status="ERROR", filter=test_filter, results=[TestCaseResult(name="(runner)", result="FAIL", messages=["no tests matched the filter"])])
            return rec, "no tests"
        results = [
            TestCaseResult(name=n, result="FAIL" if n in self.failing else "PASS", messages=["Expected 0, got 30"] if n in self.failing else [])
            for n in HEALTH_TESTS
            if n.startswith(test_filter)
        ]
        failed = sum(1 for r in results if r.result == "FAIL")
        rec = TestRunRecord(status="FAILED" if failed else "PASSED", filter=test_filter, passed=len(results) - failed, failed=failed, results=results)
        return rec, "\n".join(f"{r.result} {r.name}" for r in results)


@pytest.fixture
def settings(tmp_path: Path):
    return load_settings(
        data_dir=tmp_path / "data",
        workspace_dir=tmp_path / "ws",
        game_repo=tmp_path / "ws" / "ShunyaGame",
        engine_root=None,
        model_provider="scripted",
        database_url="",
        redis_url="",
    )


@pytest.fixture
def make_studio(settings):
    studios: list[Studio] = []

    async def _make(*, scripts=None, inject=True, build=None, tests=None, **kwargs) -> Studio:
        provider = ScriptedProvider({**demo_scripts(inject_compile_error=inject), **(scripts or {})})
        studio = Studio(settings, provider=provider, build=build or FakeBuildService(), tests=tests or FakeTestService(), **kwargs)
        studios.append(studio)
        return await studio.start()

    yield _make
    # teardown is sync; studios are stopped explicitly by tests or here via a fresh loop-safe close
    for s in studios:
        s.store.close()


async def wait_for(predicate, timeout: float = 20.0, interval: float = 0.02):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(interval)
    raise AssertionError("condition not met in time")


async def run_to_approval(studio: Studio, request: str = "Create a simple Unreal health component."):
    feature = await studio.orchestrator.submit_feature(request)
    approval = await wait_for(lambda: next(iter(studio.store.approvals.list(status=str(ApprovalStatus.PENDING))), None))
    return feature, approval


def child_tasks(studio: Studio, feature_id: str):
    return [t for t in studio.store.tasks.list(limit=1000) if t.parent_id == feature_id]


def status_of(studio: Studio, task_id: str) -> TaskStatus:
    return studio.store.tasks.get(task_id).status
