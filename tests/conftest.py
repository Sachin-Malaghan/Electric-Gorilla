from __future__ import annotations

import asyncio
import json
import re
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
from shunya.tools.content.generators import generate_texture
from shunya.tools.unreal_build import IBuildService, ITestService
from shunya.tools.unreal_content import IContentService, IPackageService, IPlaytestService

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
        """'Runs' whatever automation tests are declared in the worktree's test sources."""
        self.calls += 1
        declared: list[str] = []
        for source in sorted(project_dir.glob("Source/**/Tests/*.cpp")):
            declared += re.findall(r'IMPLEMENT_SIMPLE_AUTOMATION_TEST\(\w+,\s*"([^"]+)"', source.read_text(encoding="utf-8"))
        names = [n for n in declared if n.startswith(test_filter) and n != "ShunyaGame.Smoke.GameModeClassExists"]
        if not names:
            rec = TestRunRecord(status="ERROR", filter=test_filter, results=[TestCaseResult(name="(runner)", result="FAIL", messages=["no tests matched the filter"])])
            return rec, "no tests"
        results = [TestCaseResult(name=n, result="FAIL" if n in self.failing else "PASS", messages=["Expected 0, got 30"] if n in self.failing else []) for n in names]
        failed = sum(1 for r in results if r.result == "FAIL")
        rec = TestRunRecord(status="FAILED" if failed else "PASSED", filter=test_filter, passed=len(results) - failed, failed=failed, results=results)
        return rec, "\n".join(f"{r.result} {r.name}" for r in results)


class FakeContentService(IContentService):
    """Stands in for the headless editor: 'assets' are small files under Content/."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.fail_kinds: set[str] = set()

    async def run(self, project_dir: Path, request: dict):
        self.requests.append(request)
        staging, production = project_dir / "Content" / "AI_Staging", project_dir / "Content" / "Shunya"
        results = []
        if request["mode"] == "apply":
            for job in request["jobs"]:
                name = job.get("name") or job["level"]
                if job["kind"] in self.fail_kinds:
                    results.append({"kind": job["kind"], "name": name, "ok": False, "error": "RuntimeError: simulated editor failure"})
                    continue
                if job["kind"] == "level_additions":
                    target = next(iter(production.rglob(f"{name}.uasset")), None)
                    if target is None:
                        results.append({"kind": job["kind"], "name": name, "ok": False, "error": f"RuntimeError: level '{name}' does not exist"})
                        continue
                    target.write_text(target.read_text(encoding="utf-8") + json.dumps(job), encoding="utf-8")
                else:
                    target = staging / job["folder"] / f"{name}.uasset"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(job), encoding="utf-8")
                results.append({"kind": job["kind"], "name": name, "ok": True, "path": "/Game/" + target.relative_to(project_dir / "Content").with_suffix("").as_posix(), "detail": "fake"})
        elif request["mode"] == "validate":
            files = sorted(staging.rglob("*.uasset")) if staging.is_dir() else []
            for name in request.get("names") or []:
                files += sorted(production.rglob(f"{name}.uasset"))
            results = [{"path": "/Game/" + f.relative_to(project_dir / "Content").with_suffix("").as_posix(), "ok": True, "asset_class": "Fake", "bytes": f.stat().st_size} for f in files]
        elif request["mode"] == "promote":
            for f in sorted(staging.rglob("*.uasset")) if staging.is_dir() else []:
                target = production / f.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                f.replace(target)
                results.append({"from": str(f), "path": "/Game/Shunya/" + f.relative_to(staging).with_suffix("").as_posix(), "ok": True})
        return {"mode": request["mode"], "ok": all(r["ok"] for r in results), "results": results}, "fake editor log"


class FakePlaytestService(IPlaytestService):
    def __init__(self) -> None:
        self.calls = 0
        self.report = {"result": "WIN", "score": 80, "orbs_remaining": 0, "time_remaining": 45.0, "health": 100, "seconds": 15.0, "avg_fps": 58.0, "worst_frame_ms": 40.0, "map": "L_Arena"}

    async def play(self, project_dir: Path, map_path: str, timeout_s: int = 240):
        self.calls += 1
        shot = project_dir / "Saved" / "Screenshots" / "Playtest.png"
        generate_texture(shot, pattern="grid", size=64, color_a=(10, 12, 20), color_b=(30, 140, 190))
        return {**self.report, "screenshot": str(shot)}, "ShunyaPlaytest: " + json.dumps(self.report)


class FakePackageService(IPackageService):
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    async def package(self, project_dir: Path, out_dir: Path, map_path: str):
        self.calls += 1
        if self.fail:
            return {"ok": False, "error": "BuildCookRun exited with code 1: simulated cook failure", "output_dir": str(out_dir), "package_seconds": 1.0}, "fake uat log"
        exe = out_dir / "Windows" / "ShunyaGame.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"MZ fake")
        smoke = {"result": "WIN", "score": 80, "orbs_remaining": 0, "avg_fps": 61.0, "seconds": 14.0}
        return {"ok": True, "output_dir": str(out_dir), "executable": str(exe), "size_mb": 0.1, "file_count": 1, "package_seconds": 1.0, "smoke_run": smoke, "screenshot": None}, "fake uat log"


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
        kwargs.setdefault("content", FakeContentService())
        kwargs.setdefault("playtest", FakePlaytestService())
        kwargs.setdefault("packager", FakePackageService())
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
