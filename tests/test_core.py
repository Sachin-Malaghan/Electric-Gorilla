"""State machine, permissions/sandbox, parsers, event log, model routing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shunya.config import load_settings
from shunya.core.events import InMemoryEventBus
from shunya.core.models import ModelRouter, classify
from shunya.core.models.anthropic_provider import strict_schema
from shunya.core.models.base import Usage
from shunya.core.models.pricing import cost_usd
from shunya.core.orchestration.approvals import assess_risk
from shunya.core.orchestration.reports import FeaturePlan
from shunya.core.permissions import PathViolation, PermissionEngine, WorkspaceSandbox
from shunya.core.persistence import Store
from shunya.core.task_engine import InvalidTransition, SqlTaskRepository, TaskService, can_transition
from shunya.shared.schemas import (
    AgentProfile,
    Event,
    EventType,
    ModelConfig,
    ModelTier,
    PermissionLevel,
    RiskLevel,
    Task,
    TaskStatus,
    TaskType,
)
from shunya.tools.unreal_build import parse_automation_report, parse_build_errors

S = TaskStatus


# ---------------------------------------------------------------- task state machine


def test_spec_happy_path_is_allowed():
    path = [S.BACKLOG, S.PLANNED, S.ASSIGNED, S.IN_PROGRESS, S.REVIEW, S.BUILD, S.QA, S.ACCEPTED, S.AWAITING_APPROVAL, S.DONE]
    assert all(can_transition(a, b) for a, b in zip(path, path[1:]))


def test_spec_loops_are_allowed():
    assert can_transition(S.REVIEW, S.CHANGES_REQUESTED) and can_transition(S.CHANGES_REQUESTED, S.IN_PROGRESS)
    assert can_transition(S.QA, S.FAILED) and can_transition(S.FAILED, S.BUG_CREATED) and can_transition(S.BUG_CREATED, S.IN_PROGRESS)


@pytest.mark.parametrize("src,dst", [(S.IN_PROGRESS, S.DONE.__class__("ACCEPTED")), (S.REVIEW, S.DONE), (S.BACKLOG, S.QA), (S.DONE, S.IN_PROGRESS), (S.CANCELLED, S.BACKLOG), (S.QA, S.DONE)])
def test_shortcuts_are_rejected(src, dst):
    assert not can_transition(src, dst)


def test_cancel_from_any_non_terminal_state():
    for s in TaskStatus:
        assert can_transition(s, S.CANCELLED) == (s not in (S.DONE, S.CANCELLED))


async def test_transition_emits_event_and_records_history(tmp_path):
    store = Store(f"sqlite:///{(tmp_path / 'a.db').as_posix()}")
    bus = InMemoryEventBus(store.events)
    tasks = TaskService(SqlTaskRepository(store), bus)
    task = await tasks.create(Task(id=tasks.repo.next_id("GAME"), type=TaskType.IMPLEMENTATION, title="t"))
    assert task.id == "GAME-1" and tasks.repo.next_id("GAME") == "GAME-2"
    await tasks.transition(task, S.PLANNED, actor="producer_01", reason="planned")
    with pytest.raises(InvalidTransition):
        await tasks.transition(task, S.QA, actor="x")
    stored = store.tasks.get(task.id)
    assert stored.status == S.PLANNED and stored.history[-1].actor == "producer_01"
    types = [e.type for e in store.events.since(0)]
    assert types == [EventType.TASK_CREATED, EventType.TASK_STATUS_CHANGED]
    store.close()


# ---------------------------------------------------------------- events


async def test_event_log_is_ordered_and_replayable(tmp_path):
    store = Store(f"sqlite:///{(tmp_path / 'e.db').as_posix()}")
    bus = InMemoryEventBus(store.events)
    seen: list[int] = []

    async def consume():
        async for e in bus.subscribe():
            seen.append(e.seq)
            if len(seen) == 3:
                return

    import asyncio

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    for i in range(3):
        await bus.publish(Event(type=EventType.TASK_CREATED, task_id=f"T{i}"))
    await asyncio.wait_for(consumer, 2)
    assert seen == [1, 2, 3]
    assert [e.seq for e in store.events.since(1)] == [2, 3]
    assert store.events.last_seq() == 3
    store.close()


# ---------------------------------------------------------------- permissions and sandbox


def _profile(**perms) -> AgentProfile:
    return AgentProfile(id="a", name="A", department="engineering", role="r", tools=["create_file", "read_file"], permissions=perms)


def test_permission_engine():
    engine = PermissionEngine()
    prog = _profile(read_code=PermissionLevel.YES, write_code=PermissionLevel.CONDITIONAL, deploy=PermissionLevel.APPROVAL)
    assert engine.check(prog, "read_file", ["read_code"], isolated_workspace=False).allowed
    assert engine.check(prog, "create_file", ["write_code"], isolated_workspace=True).allowed
    assert not engine.check(prog, "create_file", ["write_code"], isolated_workspace=False).allowed  # conditional: only in a worktree
    assert not engine.check(prog, "compile_project", ["read_code"], isolated_workspace=True).allowed  # tool not granted
    d = engine.check(prog, "read_file", ["deploy"], isolated_workspace=True)
    assert not d.allowed and d.needs_approval
    assert not engine.check(_profile(), "read_file", ["read_code"], isolated_workspace=True).allowed  # default deny


def test_sandbox_blocks_escapes_and_protected_paths(tmp_path):
    (tmp_path / "Source").mkdir()
    sb = WorkspaceSandbox(tmp_path, writable_globs=["Source/*"])
    assert sb.resolve("Source/A.cpp", for_write=True) == (tmp_path / "Source" / "A.cpp").resolve()
    for bad in ["../outside.txt", "Source/../../x", "C:\\Windows\\system32\\x", "/etc/passwd", ".git/config", ""]:
        with pytest.raises(PathViolation):
            sb.resolve(bad)
    for protected in ["Source/Game/Game.Build.cs", "Source/Game.Target.cs", "Config/DefaultEngine.ini", "ShunyaGame.uproject", "Binaries/Win64/x.dll"]:
        with pytest.raises(PathViolation):
            sb.resolve(protected, for_write=True)
    with pytest.raises(PathViolation):  # readable but outside writable globs
        sb.resolve("Docs/readme.md", for_write=True)
    assert sb.resolve("Config/DefaultEngine.ini")  # reading config is fine
    with pytest.raises(PathViolation):  # never write to a non-isolated checkout
        WorkspaceSandbox(tmp_path, writable_globs=["Source/*"], isolated=False).resolve("Source/A.cpp", for_write=True)


# ---------------------------------------------------------------- parsers

MSVC_LOG = r"""
[5/9] Compile [x64] HealthComponent.cpp
C:\ws\GAME-1\Source\ShunyaGame\Private\Components\HealthComponent.cpp(58,45): error C2065: 'MaxHeath': undeclared identifier
C:\ws\GAME-1\Source\ShunyaGame\Private\Components\HealthComponent.cpp(58,45): error C2065: 'MaxHeath': undeclared identifier
C:\ws\GAME-1\Source\ShunyaGame\Public\Components\HealthComponent.h(12): warning C4996: deprecated
Module.ShunyaGame.cpp.obj : error LNK2019: unresolved external symbol "void Foo(void)"
C:\ws\GAME-1\Source\ShunyaGame\Public\X.h(7): Error: Unrecognized type 'FBogus' - type must be a UCLASS, USTRUCT, UENUM, or global delegate
Result: Failed (OtherCompilationError)
"""


def test_parse_build_errors():
    diags = parse_build_errors(MSVC_LOG)
    assert [d.code for d in diags] == ["C2065", "LNK2019", ""]
    assert diags[0].line == 58 and diags[0].column == 45 and "MaxHeath" in diags[0].message
    assert diags[2].line == 7 and "FBogus" in diags[2].message
    assert any(d.severity == "warning" for d in parse_build_errors(MSVC_LOG, include_warnings=True))
    assert parse_build_errors("Result: Succeeded\nTotal execution time: 3s") == []


def test_parse_automation_report(tmp_path):
    (tmp_path / "index.json").write_text(
        json.dumps({"succeeded": 1, "failed": 1, "tests": [
            {"fullTestPath": "ShunyaGame.Health.A", "state": "Success", "duration": 0.01, "entries": []},
            {"fullTestPath": "ShunyaGame.Health.B", "state": "Fail", "entries": [{"event": {"type": "Error", "message": "Expected 0, got 30"}}]},
        ]}),
        encoding="utf-8",
    )
    results = parse_automation_report(tmp_path, "")
    assert [(r.name, r.result) for r in results] == [("ShunyaGame.Health.A", "PASS"), ("ShunyaGame.Health.B", "FAIL")]
    assert results[1].messages == ["Expected 0, got 30"]
    log = "LogAutomationController: Test Completed. Result={Success} Name={A} Path={ShunyaGame.Health.A}"
    assert parse_automation_report(tmp_path / "missing", log)[0].result == "PASS"


# ---------------------------------------------------------------- models


def test_model_routing_and_pricing():
    assert classify("Rename variable foo") == ModelTier.FAST
    assert classify("Implement a health component") == ModelTier.STANDARD
    assert classify("Architect the networking system with replication") == ModelTier.STRONG
    router = ModelRouter(load_settings())
    assert router.resolve(ModelConfig(tier=ModelTier.STANDARD), "investigate a difficult crash").tier == ModelTier.STRONG
    assert router.resolve(ModelConfig(tier=ModelTier.STRONG), "rename variable").tier == ModelTier.STRONG  # profile tier is the floor
    assert router.resolve(ModelConfig(), "rename variable").effort == "low"
    assert cost_usd("claude-opus-5-5", Usage(input_tokens=1_000_000, output_tokens=1_000_000)) == pytest.approx(24.0)
    assert cost_usd("scripted-demo", Usage(input_tokens=10_000)) == 0.0


def test_strict_schema_closes_objects():
    schema = strict_schema(FeaturePlan.model_json_schema())
    assert schema["additionalProperties"] is False and set(schema["required"]) == set(schema["properties"])
    task = schema["$defs"]["PlannedTask"]
    assert task["additionalProperties"] is False and "acceptance_criteria" in task["required"]


def test_risk_is_computed_from_facts():
    low, _ = assess_risk(changed_files=["Source/A.cpp"], diff="+a\n-b\n", build_status="PASSED", tests_status="PASSED")
    assert low == RiskLevel.LOW
    high, reasons = assess_risk(changed_files=["Source/G/G.Build.cs"], diff="+x\n", build_status="PASSED", tests_status="PASSED")
    assert high == RiskLevel.HIGH and "dependency" in reasons[0]
    unverified, reasons = assess_risk(changed_files=["Source/A.cpp"], diff="+a\n", build_status="SKIPPED", tests_status="NOT_RUN")
    assert unverified == RiskLevel.HIGH and len(reasons) == 2
    assert assess_risk(changed_files=["Source/A.cpp"], diff="\ndeleted file mode 100644\n", build_status="PASSED", tests_status="PASSED")[0] == RiskLevel.HIGH


def test_agent_definitions_load():
    from shunya.core.agent_runtime import AgentRegistry

    registry = AgentRegistry(Path(__file__).resolve().parent.parent / "agents").load()
    assert len(registry.all()) >= 40
    for capability in ("director", "producer", "programmer", "reviewer", "qa", "build"):
        assert registry.with_capability(capability), capability
    # independence: nobody who can write code can also merge or deploy without approval
    for p in registry.all():
        assert p.permissions.get("merge", PermissionLevel.NO) == PermissionLevel.NO
        assert p.permissions.get("deploy", PermissionLevel.NO) in (PermissionLevel.NO, PermissionLevel.APPROVAL)
    reviewer = registry.with_capability("reviewer")[0]
    qa = registry.with_capability("qa")[0]
    assert "create_file" not in reviewer.tools and "patch_file" not in qa.tools
