"""The bounded agent loop: budgets, repeated-error detection, pause/cancel, permissions, validation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from shunya.core.agent_runtime import RunControl, RunRequest
from shunya.core.models.scripted_provider import ScriptedProvider, call, calls
from shunya.core.permissions import WorkspaceSandbox
from shunya.shared.schemas import AgentState, EventType, RunStatus

from .conftest import wait_for


class Report(BaseModel):
    summary: str
    files: list[str] = []


async def _run(make_studio, script, *, agent_id="gameplay_programmer_01", control=None, mutate=None, isolated=True):
    studio = await make_studio(scripts={"programmer": script})
    agent = studio.registry.get(agent_id).model_copy(deep=True)
    if mutate:
        mutate(agent)
    sandbox = WorkspaceSandbox(Path(studio.settings.game_repo), writable_globs=agent.write_globs, isolated=isolated)
    req = RunRequest(agent=agent, purpose="unit test", brief="## Task\nDo the thing.", output_model=Report, control=control or RunControl(), sandbox=sandbox)
    outcome = await studio.runner.run(req)
    return studio, outcome


async def test_successful_run_records_everything(make_studio):
    def script(ctx):
        if not ctx.called("read_file"):
            return call("read_file", path="Source/ShunyaGame/ShunyaGame.Build.cs")
        return call("submit_report", summary="done", files=["a"])

    studio, out = await _run(make_studio, script)
    assert out.ok and out.report.summary == "done"
    run = studio.store.runs.get(out.run.id)
    assert run.status == RunStatus.SUCCEEDED and run.iterations == 2 and run.tool_calls == 2 and run.llm_calls == 2
    assert run.files_inspected == ["Source/ShunyaGame/ShunyaGame.Build.cs"]
    assert [c.tool for c in studio.store.tool_calls.list(agent_id="gameplay_programmer_01")] == ["read_file", "submit_report"]
    assert len(studio.store.cost_records.list()) == 2
    types = [e.type for e in studio.store.events.since(0) if e.run_id == run.id]
    assert types[0] == EventType.AGENT_STARTED and types[-1] == EventType.AGENT_COMPLETED
    assert EventType.AGENT_TOOL_CALLED in types and EventType.AGENT_STATUS_CHANGED in types
    assert studio.statuses.get("gameplay_programmer_01").state == AgentState.SUCCESS
    assert any(m.agent_id == "gameplay_programmer_01" for m in studio.store.memories.list())  # episodic memory written


async def test_max_iterations_stops_a_looping_agent(make_studio):
    counter = iter(range(10_000))

    def script(ctx):  # never finishes: keeps listing different folders
        return call("list_dir", path="Source", depth=1 + next(counter) % 5)

    studio, out = await _run(make_studio, script, mutate=lambda a: setattr(a, "max_iterations", 5))
    assert not out.ok and out.run.status == RunStatus.BUDGET_EXCEEDED and "max iterations" in out.run.error
    assert out.run.iterations == 5
    assert studio.statuses.get("gameplay_programmer_01").state == AgentState.BLOCKED
    assert any(e.type == EventType.AGENT_ESCALATED for e in studio.store.events.since(0))


async def test_tool_call_limit_and_token_budget(make_studio):
    def script(ctx):
        return calls(("list_dir", {"path": "Source"}), ("list_dir", {"path": "Config"}), ("list_dir", {"path": "Docs"}))

    _, out = await _run(make_studio, script, mutate=lambda a: setattr(a, "max_tool_calls", 4))
    assert out.run.status == RunStatus.BUDGET_EXCEEDED and "tool-call limit" in out.run.error and out.run.tool_calls == 4

    _, out = await _run(make_studio, lambda ctx: call("list_dir", path="Source"), mutate=lambda a: setattr(a, "token_budget", 50))
    assert out.run.status == RunStatus.BUDGET_EXCEEDED and "token budget" in out.run.error


async def test_repeated_error_escalates(make_studio):
    def script(ctx):
        return call("read_file", path="Source/DoesNotExist.cpp")

    _, out = await _run(make_studio, script)
    assert out.run.status == RunStatus.ESCALATED and "same error occurred 3 times" in out.run.error
    assert out.run.tool_calls == 3


async def test_agent_that_never_submits_is_escalated(make_studio):
    from shunya.core.models.scripted_provider import ScriptStep

    _, out = await _run(make_studio, lambda ctx: ScriptStep(text="I think I am done."))
    assert out.run.status == RunStatus.ESCALATED and "without submitting" in out.run.error
    assert out.run.llm_calls == 3  # initial + two nudges


async def test_invalid_report_is_rejected_then_corrected(make_studio):
    def script(ctx):
        if not ctx.called("submit_report"):
            return call("submit_report", files=["x"])  # missing required 'summary'
        assert ctx.last("submit_report").is_error and "summary" in ctx.last("submit_report").result
        return call("submit_report", summary="fixed")

    _, out = await _run(make_studio, script)
    assert out.ok and out.report.summary == "fixed"


async def test_permissions_are_enforced_by_code_not_by_the_model(make_studio):
    seen: dict[str, str] = {}

    def script(ctx):
        attempts = [
            ("create_file", {"path": "Config/DefaultEngine.ini", "content": "x", "overwrite": True}),  # protected
            ("create_file", {"path": "../escape.txt", "content": "x"}),  # outside workspace
            ("create_file", {"path": "Source/ShunyaGame/ShunyaGame.Build.cs", "content": "x", "overwrite": True}),  # protected
            ("spawn_actor", {"class_path": "/Script/Engine.PointLight"}),  # tool not granted
            ("merge_branch", {}),  # no such tool exists at all
        ]
        if len(ctx.exchanges) < len(attempts):
            return calls(attempts[len(ctx.exchanges)])
        for e in ctx.exchanges:
            seen[f"{e.name}:{e.arguments.get('path', '')}"] = e.result
            assert e.is_error
        return call("submit_report", summary="all refused")

    studio, out = await _run(make_studio, script)
    assert out.ok
    assert "protected" in seen["create_file:Config/DefaultEngine.ini"]
    assert "escapes the workspace" in seen["create_file:../escape.txt"]
    assert "PERMISSION DENIED" in seen["spawn_actor:"] and "unknown tool" in seen["merge_branch:"]
    assert not (Path(studio.settings.game_repo).parent / "escape.txt").exists()
    assert "x" != (Path(studio.settings.game_repo) / "Config/DefaultEngine.ini").read_text(encoding="utf-8")


async def test_writes_denied_outside_an_isolated_worktree(make_studio):
    def script(ctx):
        if not ctx.exchanges:
            return call("create_file", path="Source/ShunyaGame/New.cpp", content="// x")
        assert ctx.exchanges[0].is_error and "isolated task workspace" in ctx.exchanges[0].result
        return call("submit_report", summary="refused")

    studio, out = await _run(make_studio, script, isolated=False)
    assert out.ok and not (Path(studio.settings.game_repo) / "Source/ShunyaGame/New.cpp").exists()


async def test_read_only_agent_cannot_write(make_studio):
    def script(ctx):
        if not ctx.exchanges:
            return call("patch_file", path="Source/ShunyaGame/Private/ShunyaGameMode.cpp", old_text="AShunyaGameMode", new_text="X")
        assert "PERMISSION DENIED" in ctx.exchanges[0].result
        return call("submit_report", summary="refused")

    studio = await make_studio(scripts={"qa": script})
    qa = studio.registry.get("qa_functional_01")
    sandbox = WorkspaceSandbox(Path(studio.settings.game_repo), writable_globs=["Source/*"], isolated=True)
    out = await studio.runner.run(RunRequest(agent=qa, purpose="t", brief="x", output_model=Report, control=RunControl(), sandbox=sandbox))
    assert out.ok


async def test_cancel_and_pause(make_studio):
    gate = asyncio.Event()

    def script(ctx):
        return call("list_dir", path="Source", depth=1 + len(ctx.exchanges) % 5)

    control = RunControl()
    studio = await make_studio(scripts={"programmer": script})
    agent = studio.registry.get("gameplay_programmer_01").model_copy(update={"max_iterations": 100000, "max_tool_calls": 100000, "token_budget": 10**12})
    sandbox = WorkspaceSandbox(Path(studio.settings.game_repo), isolated=True)
    task = asyncio.create_task(studio.runner.run(RunRequest(agent=agent, purpose="t", brief="x", output_model=Report, control=control, sandbox=sandbox)))
    await wait_for(lambda: studio.store.tool_calls.count() >= 2)
    control.pause()
    await asyncio.sleep(0.1)
    frozen = studio.store.tool_calls.count()
    await asyncio.sleep(0.15)
    assert studio.store.tool_calls.count() == frozen and not task.done()  # paused: no progress, still alive
    control.resume()
    await wait_for(lambda: studio.store.tool_calls.count() > frozen)
    control.cancel()
    out = await asyncio.wait_for(task, 5)
    assert out.run.status == RunStatus.CANCELLED
    assert studio.statuses.get("gameplay_programmer_01").state == AgentState.IDLE
    gate.set()


async def test_provider_failure_is_bounded(make_studio):
    from shunya.core.models.base import ModelProviderError

    def script(ctx):
        raise ModelProviderError("api down")

    import shunya.core.agent_runtime.runner as runner_mod

    original = asyncio.sleep
    runner_mod.asyncio.sleep = lambda *_: original(0)  # skip backoff waits
    try:
        _, out = await _run(make_studio, script)
    finally:
        runner_mod.asyncio.sleep = original
    assert out.run.status == RunStatus.FAILED and "api down" in out.run.error and out.run.llm_calls == 0
