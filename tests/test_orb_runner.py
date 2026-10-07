"""The all-departments feature: every track (code, doc, content), every department, one game."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shunya.demo.orb_runner import code, screenplay
from shunya.shared.schemas import AgentState, ApprovalStatus, EventType, RiskLevel, TaskStatus
from shunya.tools.content import generators as gen
from shunya.tools.git_tools import git

from .conftest import FakeContentService, FakePackageService, FakePlaytestService, child_tasks, status_of, the_repo

S = TaskStatus
REQUEST = "Build Orb Runner: a small arena game where the player collects orbs while a drone chases them."


async def _run(studio, timeout=240.0):
    """Runs the feature; the studio owner (this test) decides whatever policy does not."""
    feature = await studio.orchestrator.submit_feature(REQUEST)
    human: list = []

    def settled():
        return status_of(studio, feature.id) in (S.DONE, S.BLOCKED)

    deadline = asyncio.get_event_loop().time() + timeout
    while not settled():
        assert asyncio.get_event_loop().time() < deadline, "feature did not settle in time"
        for approval in studio.store.approvals.list(status=str(ApprovalStatus.PENDING)):
            human.append(approval)
            await studio.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
        await asyncio.sleep(0.1)
    feature.result["human_approvals"] = human
    return feature


async def test_every_department_delivers_and_the_game_is_merged(make_studio, settings):
    settings.auto_approve_max_risk = "LOW"
    settings.max_concurrent_tasks = 6
    content, playtest = FakeContentService(), FakePlaytestService()
    studio = await make_studio(inject=False, content=content, playtest=playtest)
    feature = await _run(studio)
    tasks = child_tasks(studio, feature.id)
    blocked = {t.title: t.result.get("blocked_reason") for t in tasks if t.status != S.DONE}
    assert not blocked, blocked
    assert status_of(studio, feature.id) == S.DONE and len(tasks) == len(screenplay.STEPS) == 34

    # every department did real work, by the capability the producer assigned
    by_title = {t.title: t for t in tasks}
    departments = {studio.registry.get(t.owner).department for t in tasks}
    assert departments == {"design", "engineering", "art", "environment", "animation", "audio", "qa", "devops", "documentation"}
    for step in screenplay.STEPS:
        task = by_title[step.title]
        owner, reviewer = studio.registry.get(task.owner), task.result["review"]["reviewer"]
        assert owner.capability == step.assignee and task.track == step.track
        assert studio.registry.get(reviewer).capability == step.reviewer and reviewer != task.owner  # independent review by the right lead

    # dependencies were respected: nothing started before what it depends on was merged
    done_at = {t.id: next(h.at for h in t.history if h.to_status == S.DONE) for t in tasks}
    for t in tasks:
        started = next(h.at for h in t.history if h.to_status == S.IN_PROGRESS)
        assert all(done_at[d] <= started for d in t.dependencies), t.title

    # the three tracks took their own routes
    code_task, doc_task, content_task = by_title["Implement the chaser drone"], by_title["Write the tuning table"], by_title["Build the arena level"]
    assert code_task.result["build"]["status"] == "PASSED" and code_task.result["qa"]["qa_agent"] == "qa_functional_01"
    assert doc_task.result["build"]["status"] == "NOT_APPLICABLE" and doc_task.result["qa"]["tests_status"] == "NOT_APPLICABLE"
    assert content_task.result["qa"]["test_run"]["filter"] == "content" and content_task.result["promoted"] == ["/Game/Shunya/Maps/L_Arena"]
    modes = [r["mode"] for r in content.requests]
    assert modes.count("promote") == 8 and modes.count("apply") == 8 and modes.count("validate") == 8

    # QA reports state real tool results, with the playtest screenshot as evidence
    play = by_title["Playtest the game"]
    assert play.result["qa"]["tests_status"] == "PASSED" and play.result["qa"]["images"]
    assert playtest.calls == 2  # gameplay QA and performance QA each played
    repo = the_repo(studio.settings)
    report = (await git(repo, "show", "develop:Docs/QA/PlaytestReport.md")).out
    assert "Verdict: **PASSED**" in report and "| Score | 80 of 80 |" in report and "| Average FPS | 58.0 |" in report
    signoff = (await git(repo, "show", "develop:Docs/QA/SignOff.md")).out
    assert "SIGNED OFF for develop" in signoff and "average 58.0 FPS" in signoff

    # the game itself is on develop: code, recipes, promoted assets, docs - and nothing on main
    files = set((await git(repo, "ls-tree", "-r", "--name-only", "develop")).out.split("\n"))
    for expected in ("Source/ShunyaGame/Public/AI/ChaserDrone.h", "Source/ShunyaGame/Private/Tools/OrbPlaytestSubsystem.cpp", "Content/Shunya/Maps/L_Arena.uasset",
                     "Content/Shunya/Audio/S_MusicLoop.uasset", "Content/Shunya/Cinematics/SEQ_Intro.uasset", "SourceArt/Generated/T_FloorGrid.png",
                     "Docs/Design/GDD.md", "Docs/Art/ConceptBoard.png", "Docs/Release/ReleaseNotes-0.1.0.md"):
        assert expected in files, expected
    assert not any(f.startswith("Content/AI_Staging/") for f in files)  # staging never reaches develop
    assert "Docs/Design/GDD.md" not in (await git(repo, "ls-tree", "-r", "--name-only", "main")).out
    game_mode = (await git(repo, "show", "develop:Source/ShunyaGame/Private/Game/OrbGameMode.cpp")).out
    assert "DefaultPawnClass = AOrbRunnerPawn::StaticClass();" in game_mode and "HUDClass = AOrbHUD::StaticClass();" in game_mode

    # approvals: all decided by the low-risk policy, each with computed risk and evidence
    approvals = studio.store.approvals.list(limit=200)
    by_policy = [a for a in approvals if a.decided_by == "policy"]
    assert len(approvals) == 34 and len(by_policy) == 33 and all(a.status == ApprovalStatus.GRANTED and a.risk_level == RiskLevel.LOW for a in by_policy)
    # packaging is never auto-approved: the owner signed off the build, with the packaging evidence attached
    (package_approval,) = feature.result["human_approvals"]
    assert package_approval.risk_level == RiskLevel.HIGH and "release packaging" in package_approval.risk_reasons[0]
    package = by_title["Package the Windows build"]
    assert package.result["qa"]["test_run"]["filter"] == "package" and package.result["qa"]["tests_status"] == "PASSED"
    build_doc = (await git(repo, "show", "develop:Docs/Release/Build-0.1.0.md")).out
    assert "Verdict: **PASSED**" in build_doc and "Smoke run | WIN - score 80" in build_doc
    assert (studio.settings.builds_dir / "orb-runner" / "v0.1.0" / "Windows" / "ShunyaGame.exe").is_file()
    assert not any("ShunyaGame.exe" in f for f in files)  # the build itself is never committed
    assert all(s.state in (AgentState.IDLE, AgentState.OFFLINE) for s in studio.statuses.all())
    offline = sorted(p.id for p in studio.registry.all() if not p.enabled)
    assert len(offline) == 9  # roles with no real work in this game stay empty desks
    kinds = {e.type for e in studio.store.events.since(0, limit=20000)}
    assert {EventType.MEETING_STARTED, EventType.BUILD_PASSED, EventType.TEST_PASSED, EventType.APPROVAL_GRANTED} <= kinds
    await studio.stop()


async def test_failed_content_blocks_instead_of_shipping(make_studio, settings):
    """The editor fails to build the level: nothing is promoted, the level task blocks, dependants never start."""
    settings.auto_approve_max_risk = "LOW"
    settings.max_concurrent_tasks = 6
    content = FakeContentService()
    content.fail_kinds = {"level"}
    studio = await make_studio(inject=False, content=content)
    feature = await _run(studio)
    assert status_of(studio, feature.id) == S.BLOCKED
    by_title = {t.title: t for t in child_tasks(studio, feature.id)}
    level = by_title["Build the arena level"]
    assert level.status == S.BLOCKED and "simulated editor failure" in level.result["blocked_reason"]
    assert by_title["Light the arena"].status == S.PLANNED and by_title["Playtest the game"].status == S.PLANNED
    assert by_title["Write the 0.1.0 release notes"].status == S.PLANNED  # no release notes for a game that was not verified
    assert by_title["Implement the QA autoplay bot"].status == S.DONE  # unrelated work still finished
    files = (await git(the_repo(studio.settings), "ls-tree", "-r", "--name-only", "develop")).out
    assert "L_Arena" not in files
    await studio.stop()


async def test_playtest_failure_is_reported_honestly_and_withholds_signoff(make_studio, settings):
    settings.auto_approve_max_risk = "LOW"
    settings.max_concurrent_tasks = 6
    playtest = FakePlaytestService()
    playtest.report = {**playtest.report, "result": "LOSE", "score": 30, "orbs_remaining": 5, "health": 0}
    studio = await make_studio(inject=False, playtest=playtest)
    feature = await _run(studio)
    assert status_of(studio, feature.id) == S.BLOCKED
    by_title = {t.title: t for t in child_tasks(studio, feature.id)}
    play = by_title["Playtest the game"]
    assert play.status == S.BLOCKED and "still failing" in play.result["blocked_reason"]
    assert "requires a passing verification run" in play.result["qa"]["gate_note"]
    assert by_title["Write the QA sign-off"].status == S.PLANNED and by_title["Package the Windows build"].status == S.PLANNED
    report = (Path(play.worktree) / "Docs/QA/PlaytestReport.md").read_text(encoding="utf-8")
    assert "Verdict: **FAILED**" in report and "| Match result | LOSE |" in report  # the report says what happened
    await studio.stop()


def test_generators_write_valid_png_and_wav(tmp_path):
    import struct
    import wave
    import zlib

    png = tmp_path / "t.png"
    gen.generate_texture(png, pattern="grid", size=64, color_a=(8, 12, 25), color_b=(25, 140, 190), cells=4)
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (64, 64)
    idat = data[data.index(b"IDAT") + 4 : data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert len(raw) == 64 * (64 * 3 + 1) and raw[1:4] == bytes((25, 140, 190)) and raw[(64 * 3 + 1) * 5 + 1 + 15:][:3] == bytes((8, 12, 25))
    wav = tmp_path / "s.wav"
    seconds = gen.generate_sound(wav, notes=[{"frequency": 440, "duration": 0.1}, {"frequency": 0, "duration": 0.05}, {"frequency": 220, "duration": 0.1, "waveform": "noise"}])
    with wave.open(str(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 44100) and abs(w.getnframes() / 44100 - seconds) < 1e-6
    assert abs(seconds - 0.25) < 0.001


def test_screenplay_is_internally_consistent():
    keys = [s.key for s in screenplay.STEPS]
    assert len(set(keys)) == len(keys) and len({s.title for s in screenplay.STEPS}) == len(keys)
    for i, s in enumerate(screenplay.STEPS):
        assert all(d in keys[:i] for d in s.depends), f"{s.key} depends on something later in the plan"
        assert s.assignee != s.reviewer
        if s.track != "doc":
            assert len(s.evidence) == len(s.criteria), s.key
        for d in s.docs:
            assert (screenplay.DOCS_DIR / d).is_file(), d
    declared = set()
    for key in code.CODE_TASK_ORDER:
        files = code.task_files(key)
        assert files, key
        for text in files.values():
            import re

            declared |= set(re.findall(r'IMPLEMENT_SIMPLE_AUTOMATION_TEST\(\w+,\s*"([^"]+)"', text))
    needed = {e for s in screenplay.STEPS if s.track == "code" for e in s.evidence}
    assert needed <= declared, needed - declared  # every criterion's evidence is a test that really exists


async def test_failed_packaging_is_reported_and_never_signed_off(make_studio, settings):
    settings.auto_approve_max_risk = "LOW"
    settings.max_concurrent_tasks = 6
    packager = FakePackageService()
    packager.fail = True
    studio = await make_studio(inject=False, packager=packager)
    feature = await _run(studio)
    assert status_of(studio, feature.id) == S.BLOCKED and not feature.result["human_approvals"]  # nothing was ever offered for sign-off
    package = {t.title: t for t in child_tasks(studio, feature.id)}["Package the Windows build"]
    assert package.status == S.BLOCKED and "requires a passing verification run" in package.result["qa"]["gate_note"]
    doc = (Path(package.worktree) / "Docs/Release/Build-0.1.0.md").read_text(encoding="utf-8")
    assert "Verdict: **FAILED**" in doc and "simulated cook failure" in doc
    await studio.stop()
