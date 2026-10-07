"""The vertical slice (spec 48, 49, 52): Producer -> Programmer -> Review -> Build -> QA -> Human approval -> merge."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shunya.core.models.demo_scripts import demo_scripts, reviewer as default_reviewer
from shunya.core.models.scripted_provider import ScriptedProvider, call
from shunya.shared.schemas import (
    AgentState,
    ApprovalStatus,
    BuildStatus,
    EventType,
    MessageType,
    RiskLevel,
    RunStatus,
    TaskStatus,
)
from shunya.studio import Studio
from shunya.tools.git_tools import git

from .conftest import FakeBuildService, FakeTestService, child_tasks, run_to_approval, status_of, the_repo, wait_for

S = TaskStatus
HEADER = "Source/ShunyaGame/Public/Components/HealthComponent.h"


async def _show(repo: Path, ref: str, path: str) -> str | None:
    res = await git(repo, "show", f"{ref}:{path}", check=False)
    return res.out if res.code == 0 else None


async def test_feature_goes_from_request_to_merged_with_evidence(make_studio):
    build, tests = FakeBuildService(), FakeTestService()
    studio = await make_studio(build=build, tests=tests)
    feature, approval = await run_to_approval(studio)
    task = child_tasks(studio, feature.id)[0]

    # Producer produced a typed task with acceptance criteria
    assert task.type == "IMPLEMENTATION" and len(task.acceptance_criteria) == 4 and task.created_by == "producer_01"
    assert task.status == S.AWAITING_APPROVAL and task.branch == f"agent/{task.id}"
    # The planning meeting was a real collaboration session
    meeting = studio.store.meetings.list()[0]
    assert meeting.status == "CLOSED" and set(meeting.participants) >= {"producer_01", "studio_director_01"} and meeting.decisions

    # Programmer worked only in the isolated worktree: develop and main are untouched before approval
    repo = the_repo(studio.settings)
    assert await _show(repo, "develop", HEADER) is None and await _show(repo, "main", HEADER) is None
    assert await _show(repo, task.branch, HEADER) is not None

    # Compile failure was captured, parsed and corrected by the agent (bounded correction)
    builds = studio.store.builds.list(task_id=task.id)
    assert [b.status for b in builds] == [BuildStatus.FAILED, BuildStatus.PASSED, BuildStatus.PASSED]
    assert builds[0].diagnostics[0].code == "C2065" and builds[0].agent_id == "gameplay_programmer_01"
    assert builds[2].agent_id == "build_engineer_01"  # the official build is not the implementer's
    assert all(b.log_artifact_id for b in builds)

    # Independent review and QA by different agents, with evidence
    owner = task.owner
    assert task.result["review"]["reviewer"] == "technical_director_01" != owner
    qa = task.result["qa"]
    assert qa["qa_agent"] == "qa_functional_01" != owner and qa["verdict"] == "PASS"
    assert qa["test_run"]["status"] == "PASSED" and qa["test_run"]["passed"] == 5 and len(qa["criteria"]) == 4
    assert all(c["met"] and c["evidence"] for c in qa["criteria"])
    assert tests.calls == 2  # programmer ran them, then QA ran them again independently

    # Approval object carries diff, evidence and computed risk
    assert approval.risk_level == RiskLevel.LOW and approval.diff_artifact_id
    assert "UHealthComponent" in studio.artifacts.read_text(approval.diff_artifact_id)
    assert set(approval.evidence) >= {"changed_files", "commit", "build", "review", "qa", "acceptance_criteria"}
    assert studio.statuses.get(owner).state == AgentState.WAITING_APPROVAL

    await studio.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
    await wait_for(lambda: status_of(studio, feature.id) == S.DONE)
    task = studio.store.tasks.get(task.id)
    assert task.status == S.DONE and task.result["merge_commit"]
    assert await _show(repo, "develop", HEADER) is not None
    assert await _show(repo, "main", HEADER) is None  # agents never touch main
    assert not Path(task.worktree).exists()
    assert studio.statuses.get(owner).state == AgentState.IDLE

    # Every operation is logged and traceable under one trace id
    events = studio.store.events.since(0, limit=5000)
    kinds = {e.type for e in events}
    assert kinds >= {
        EventType.TASK_CREATED, EventType.TASK_ASSIGNED, EventType.TASK_STARTED, EventType.AGENT_STARTED, EventType.AGENT_TOOL_CALLED,
        EventType.AGENT_STATUS_CHANGED, EventType.BUILD_STARTED, EventType.BUILD_FAILED, EventType.BUILD_PASSED, EventType.TEST_STARTED,
        EventType.TEST_PASSED, EventType.MEETING_STARTED, EventType.MEETING_ENDED, EventType.APPROVAL_REQUIRED, EventType.APPROVAL_GRANTED,
        EventType.TASK_COMPLETED,
    }
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    assert all(r.trace_id == task.trace_id for r in studio.store.runs.list(task_id=task.id))
    states = [e.payload["to"] for e in events if e.type == EventType.AGENT_STATUS_CHANGED and e.agent_id == owner]
    for expected in ("MEETING", "READING", "CODING", "COMPILING", "DEBUGGING", "TESTING", "WAITING_APPROVAL", "IDLE"):
        assert expected in states, expected
    await studio.stop()


async def test_review_can_send_work_back(make_studio):
    rounds = {"n": 0}

    def strict_reviewer(ctx):
        if not ctx.called("git_diff"):
            return call("git_diff")
        if rounds["n"] == 0:
            rounds["n"] += 1
            return call("submit_report", verdict="CHANGES_REQUESTED", summary="Heal must document dead behaviour.",
                        findings=[{"severity": "MAJOR", "file": HEADER, "line": 31, "comment": "Document that Heal is ignored once dead."}])
        return default_reviewer(ctx)

    studio = await make_studio(scripts={"reviewer": strict_reviewer}, inject=False)
    feature, approval = await run_to_approval(studio)
    task = child_tasks(studio, feature.id)[0]
    path = [t.to_status for t in task.history]
    assert path.count(S.REVIEW) == 2 and S.CHANGES_REQUESTED in path
    assert path.index(S.CHANGES_REQUESTED) < len(path) - 1 - path[::-1].index(S.REVIEW)
    feedback = [m for m in studio.store.messages.list(task_id=task.id) if m.type == MessageType.REVIEW_FEEDBACK]
    assert feedback and feedback[0].sender == "technical_director_01" and feedback[0].receiver == task.owner
    # the second implementation run was briefed with the reviewer's finding
    impl_runs = [r for r in studio.store.runs.list(task_id=task.id) if r.purpose == "implement task"]
    assert len(impl_runs) == 2
    await studio.orchestrator.cancel(feature.id)
    await studio.stop()


async def test_programmer_reports_failing_tests_honestly_and_escalates(make_studio):
    """The implementer's own test run fails: it reports blocked, nothing reaches approval, the supervisor is notified."""
    tests = FakeTestService()
    tests.failing = {"ShunyaGame.Health.DamageCannotGoBelowZero"}

    def lying_qa(ctx):
        if not ctx.called("run_automation_tests"):
            return call("run_automation_tests", filter="ShunyaGame.Health")
        crit = [{"criterion": c, "met": True, "evidence": "looks fine"} for c in ("a", "b", "c", "d")]
        return call("submit_report", verdict="PASS", summary="All good!", criteria=crit, defects=[])

    studio = await make_studio(scripts={"qa": lying_qa}, tests=tests, inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: status_of(studio, feature.id) == S.BLOCKED, timeout=30)
    task = child_tasks(studio, feature.id)[0]
    assert task.status == S.BLOCKED
    # The programmer reported honestly that its own test run failed, so it never reached QA with a false claim...
    assert "blocked" in task.result["blocked_reason"].lower()
    assert not studio.store.approvals.list()  # nothing was ever offered for approval
    escalations = [m for m in studio.store.messages.list(task_id=task.id) if m.type == MessageType.ESCALATION]
    assert escalations and escalations[0].receiver == "technical_director_01"
    assert studio.statuses.get(task.owner).state == AgentState.BLOCKED
    await studio.stop()


async def test_qa_gate_overrides_false_pass_then_bug_loop_is_bounded(make_studio):
    tests = FakeTestService()

    def lying_qa(ctx):
        if not ctx.called("run_automation_tests"):
            tests.failing = {"ShunyaGame.Health.DeathEventFiresOnce"}  # breaks between the programmer's run and QA's
            return call("run_automation_tests", filter="ShunyaGame.Health")
        crit = [{"criterion": c, "met": True, "evidence": "trust me"} for c in ("a", "b", "c", "d")]
        tests.failing = set()
        return call("submit_report", verdict="PASS", summary="All good!", criteria=crit, defects=[])

    studio = await make_studio(scripts={"qa": lying_qa}, tests=tests, inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: status_of(studio, feature.id) == S.BLOCKED, timeout=40)
    task = child_tasks(studio, feature.id)[0]
    path = [t.to_status for t in task.history]
    assert S.ACCEPTED not in path  # the false PASS never became an acceptance
    assert path.count(S.FAILED) == studio.settings.max_qa_rounds + 1 and path.count(S.BUG_CREATED) == studio.settings.max_qa_rounds
    assert "requires evidence" in task.result["qa"]["gate_note"]
    bugs = studio.store.bugs.list(task_id=task.id)
    assert bugs and bugs[0].reporter == "qa_functional_01"
    assert any(e.type == EventType.BUG_CREATED for e in studio.store.events.since(0, limit=5000))
    assert "still failing" in task.result["blocked_reason"]
    await studio.stop()


async def test_official_build_failure_returns_to_engineering(make_studio):
    class FlakyOfficialBuild(FakeBuildService):
        async def compile(self, project_dir):
            self.always_fail = self.calls == 1  # programmer's build passes, the Build Engineer's first one fails
            return await FakeBuildService.compile(self, project_dir)

    build = FlakyOfficialBuild()
    studio = await make_studio(build=build, inject=False)
    feature, approval = await run_to_approval(studio)
    task = child_tasks(studio, feature.id)[0]
    path = [t.to_status for t in task.history]
    assert [S.BUILD, S.FAILED, S.BUG_CREATED, S.IN_PROGRESS] == path[path.index(S.BUILD):path.index(S.BUILD) + 4]
    assert any(m.type == MessageType.BUILD_FAILURE for m in studio.store.messages.list(task_id=task.id))
    assert any(m.kind == "operational" for m in studio.store.memories.list())  # failure remembered as operational memory
    await studio.orchestrator.cancel(feature.id)
    await studio.stop()


async def test_editor_side_effects_on_protected_files_never_reach_the_commit(make_studio):
    """Running the Unreal Editor rewrites Config/*.ini; that must not ride along into an agent's commit."""

    class EditorLikeTests(FakeTestService):
        async def run_tests(self, project_dir, test_filter):
            (project_dir / "Config" / "DefaultInput.ini").write_text("[/Script/Engine.InputSettings]\n", encoding="utf-8")
            engine_ini = project_dir / "Config" / "DefaultEngine.ini"
            engine_ini.write_text(engine_ini.read_text(encoding="utf-8") + "\n[Editor]\nTouched=True\n", encoding="utf-8")
            return await FakeTestService.run_tests(self, project_dir, test_filter)

    studio = await make_studio(tests=EditorLikeTests(), inject=False)
    feature, approval = await run_to_approval(studio)
    changed = approval.evidence["changed_files"]
    assert changed and all(f.startswith("Source/") for f in changed), changed
    assert approval.risk_level == RiskLevel.LOW
    assert "DefaultInput.ini" not in studio.artifacts.read_text(approval.diff_artifact_id)
    await studio.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
    await wait_for(lambda: status_of(studio, feature.id) == S.DONE)
    assert await _show(the_repo(studio.settings), "develop", "Config/DefaultInput.ini") is None
    await studio.stop()


async def test_human_rejection_cancels_and_never_merges(make_studio):
    studio = await make_studio(inject=False)
    feature, approval = await run_to_approval(studio)
    task = child_tasks(studio, feature.id)[0]
    await studio.approvals.decide(approval.id, granted=False, decided_by="studio_owner", comment="not now")
    await wait_for(lambda: status_of(studio, task.id) == S.CANCELLED)
    assert await _show(the_repo(studio.settings), "develop", HEADER) is None
    assert studio.store.approvals.get(approval.id).status == ApprovalStatus.REJECTED
    await studio.stop()


async def test_human_rejection_with_rework_goes_back_to_engineering(make_studio):
    studio = await make_studio(inject=False)
    feature, approval = await run_to_approval(studio)
    task_id = child_tasks(studio, feature.id)[0].id
    await studio.approvals.decide(approval.id, granted=False, decided_by="studio_owner", comment="Add a SetMaxHealth API", rework=True)
    second = await wait_for(lambda: next((a for a in studio.store.approvals.list(status=str(ApprovalStatus.PENDING)) if a.id != approval.id), None))
    task = studio.store.tasks.get(task_id)
    path = [t.to_status for t in task.history]
    assert S.REJECTED in path and path.count(S.AWAITING_APPROVAL) == 2
    await studio.approvals.decide(second.id, granted=True, decided_by="studio_owner")
    await wait_for(lambda: status_of(studio, feature.id) == S.DONE)
    await studio.stop()


async def test_cancel_mid_run_stops_agents_and_cleans_up(make_studio):
    release = asyncio.Event()

    class SlowBuild(FakeBuildService):
        async def compile(self, project_dir):
            await release.wait()
            return await FakeBuildService.compile(self, project_dir)

    studio = await make_studio(build=SlowBuild(), inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: any(s.state == AgentState.COMPILING for s in studio.statuses.all()))
    task = child_tasks(studio, feature.id)[0]
    await studio.orchestrator.cancel(feature.id)
    release.set()
    await wait_for(lambda: status_of(studio, task.id) == S.CANCELLED and status_of(studio, feature.id) == S.CANCELLED)
    await studio.orchestrator.wait_idle(5)
    assert all(s.state in (AgentState.IDLE, AgentState.OFFLINE) for s in studio.statuses.all())
    assert not Path(studio.store.tasks.get(task.id).worktree).exists()
    assert any(r.status == RunStatus.CANCELLED for r in studio.store.runs.list(task_id=task.id))
    await studio.stop()


async def test_pause_and_resume_task(make_studio):
    studio = await make_studio(inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: child_tasks(studio, feature.id))
    await studio.orchestrator.pause(feature.id)
    # pause takes effect at the next checkpoint: let the in-flight step finish, then nothing may happen
    frozen = -1
    for _ in range(40):
        await asyncio.sleep(0.5)
        if studio.store.events.last_seq() == frozen:
            break
        frozen = studio.store.events.last_seq()
    await asyncio.sleep(1.0)
    assert studio.store.events.last_seq() == frozen  # nothing happens while paused
    assert studio.store.tasks.get(feature.id).paused
    assert not studio.store.approvals.list()
    await studio.orchestrator.resume(feature.id)
    await wait_for(lambda: studio.store.approvals.list(status=str(ApprovalStatus.PENDING)))
    assert not studio.store.tasks.get(feature.id).paused
    await studio.orchestrator.cancel(feature.id)
    await studio.stop()


async def test_blocked_task_can_be_retried_by_a_human(make_studio):
    build = FakeBuildService()
    build.always_fail = True
    studio = await make_studio(build=build, inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: status_of(studio, feature.id) == S.BLOCKED, timeout=30)
    task = child_tasks(studio, feature.id)[0]
    assert task.status == S.BLOCKED and "blocked" in task.result["blocked_reason"].lower()
    build.always_fail = False  # the human fixed the environment
    await studio.orchestrator.retry(task.id, note="Toolchain repaired, please try again.")
    approval = await wait_for(lambda: next(iter(studio.store.approvals.list(status=str(ApprovalStatus.PENDING))), None), timeout=30)
    await studio.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
    await wait_for(lambda: status_of(studio, feature.id) == S.DONE)
    await studio.stop()


async def test_state_survives_restart_and_pipeline_resumes(make_studio, settings):
    """Kill the studio while a task awaits approval; a new process picks it up and finishes it."""
    studio = await make_studio(inject=False)
    feature, approval = await run_to_approval(studio)
    task_id = child_tasks(studio, feature.id)[0].id
    seq_before = studio.store.events.last_seq()
    await studio.stop()

    provider = ScriptedProvider(demo_scripts(inject_compile_error=False))
    reborn = await Studio(settings, provider=provider, build=FakeBuildService(), tests=FakeTestService()).start()
    try:
        assert reborn.store.tasks.get(task_id).status == S.AWAITING_APPROVAL
        assert reborn.store.approvals.get(approval.id).status == ApprovalStatus.PENDING
        assert reborn.store.events.last_seq() >= seq_before
        assert any(e.type == EventType.STUDIO_RECOVERED for e in reborn.store.events.since(seq_before))
        await wait_for(lambda: reborn.orchestrator.is_running(feature.id))
        await reborn.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
        await wait_for(lambda: status_of(reborn, feature.id) == S.DONE)
        assert await _show(the_repo(settings), "develop", HEADER) is not None
    finally:
        await reborn.stop()


async def test_restart_mid_implementation_resumes_from_persisted_status(make_studio, settings):
    release = asyncio.Event()

    class SlowBuild(FakeBuildService):
        async def compile(self, project_dir):
            await release.wait()
            return await FakeBuildService.compile(self, project_dir)

    studio = await make_studio(build=SlowBuild(), inject=False)
    feature = await studio.orchestrator.submit_feature("Create a simple Unreal health component.")
    await wait_for(lambda: any(s.state == AgentState.COMPILING for s in studio.statuses.all()))
    task_id = child_tasks(studio, feature.id)[0].id
    await studio.stop()  # crash while the programmer is compiling
    release.set()

    provider = ScriptedProvider(demo_scripts(inject_compile_error=False))
    reborn = await Studio(settings, provider=provider, build=FakeBuildService(), tests=FakeTestService()).start()
    try:
        interrupted = [r for r in reborn.store.runs.list(task_id=task_id) if r.status == RunStatus.INTERRUPTED]
        assert interrupted, "the orphaned run must be marked interrupted, not left RUNNING"
        approval = await wait_for(lambda: next(iter(reborn.store.approvals.list(status=str(ApprovalStatus.PENDING))), None), timeout=30)
        assert approval.task_id == task_id
        await reborn.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
        await wait_for(lambda: status_of(reborn, feature.id) == S.DONE)
    finally:
        await reborn.stop()


async def test_unsupported_request_blocks_with_a_clear_reason(make_studio, monkeypatch):
    import shunya.core.agent_runtime.runner as runner_mod

    real_sleep = asyncio.sleep
    monkeypatch.setattr(runner_mod.asyncio, "sleep", lambda d=0, *a: real_sleep(min(d, 0.01)))
    studio = await make_studio()
    feature = await studio.orchestrator.submit_feature("Add stealth takedowns to the player.")
    await wait_for(lambda: status_of(studio, feature.id) == S.BLOCKED)
    assert "SHUNYA_MODEL_PROVIDER=anthropic" in studio.store.tasks.get(feature.id).result["blocked_reason"]
    await studio.stop()
