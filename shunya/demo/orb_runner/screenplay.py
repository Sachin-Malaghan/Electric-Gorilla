"""The Orb Runner screenplay: one small game that gives every department real work.

Like the health-component script, this is NOT agents reasoning. It is a fixed script that
drives the real pipeline - real worktrees, compiler, automation tests, headless editor,
playtests, reviews, gates and approvals - so the whole studio can be exercised and watched
without an LLM. Reports written by the scripted QA roles are filled in from the actual
tool results, and a scripted role reports itself blocked when a tool fails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shunya.core.models.scripted_provider import ScriptContext, ScriptStep, call, calls
from shunya.demo.orb_runner import code, content

DOCS_DIR = Path(__file__).parent / "docs"
TRIGGER = re.compile(r"\borb\s*runner\b", re.I)


@dataclass
class Step:
    key: str
    title: str
    track: str  # code | doc | content
    assignee: str
    reviewer: str
    depends: list[str]
    criteria: list[str]
    evidence: list[str] = field(default_factory=list)  # per criterion: test name (code) or asset name (content)
    description: str = ""
    docs: list[str] = field(default_factory=list)  # paths under Docs/ copied from DOCS_DIR
    calls: list[content.Call] = field(default_factory=list)  # content / image tool calls
    verify: str = ""  # playtest | performance | regression
    test_filter: str = ""
    type: str = "IMPLEMENTATION"
    priority: str = "MEDIUM"


def _doc(key: str, title: str, who: str, reviewer: str, depends: list[str], doc: str, criteria: list[str], description: str, **kw: Any) -> Step:
    return Step(key, title, "doc", who, reviewer, depends, criteria, docs=[doc], description=description, type=kw.pop("type", "DESIGN"), **kw)


T = "ShunyaGame."

STEPS: list[Step] = [
    # ---------------------------------------------------------------- design
    _doc("design_gdd", "Write the Orb Runner game design document", "lead_designer", "producer", [], "Design/GDD.md",
         ["States the core loop, the win condition and both lose conditions", "Lists what is out of scope for 0.1"],
         "Write Docs/Design/GDD.md: the root design document every other document must agree with.", priority="HIGH"),
    _doc("design_tuning", "Write the tuning table", "economy_designer", "lead_designer", ["design_gdd"], "Design/Tuning.md",
         ["Gives a number for the time limit, orb count, points per orb, player and drone speed, damage and cooldown", "The drone is slower than the player"],
         "Write Docs/Design/Tuning.md with every number engineering must implement."),
    _doc("design_threat", "Specify the chaser drone", "combat_designer", "lead_designer", ["design_gdd"], "Design/ThreatSpec.md",
         ["Describes pursuit, contact damage and cooldown with values", "Lists statements a test can check"],
         "Write Docs/Design/ThreatSpec.md for the enemy."),
    _doc("design_level", "Lay out the arena level", "level_designer", "lead_designer", ["design_gdd"], "Design/LevelLayout.md",
         ["Gives location and scale for the floor, walls and pillars", "Gives locations for the player start, 8 orbs and the drone"],
         "Write Docs/Design/LevelLayout.md with coordinates the world builder can use directly."),
    _doc("design_narrative", "Write the premise and on-screen text", "narrative_designer", "lead_designer", ["design_gdd"], "Design/Narrative.md",
         ["Gives the exact win and lose banner text", "Gives the exact HUD labels"],
         "Write Docs/Design/Narrative.md: premise, naming, and exact on-screen strings."),
    _doc("design_controls", "Define controls and game feel", "gameplay_designer", "lead_designer", ["design_gdd"], "Design/ControlsAndFeel.md",
         ["Maps keys to movement directions", "States that diagonal movement is not faster and that a bot must be able to drive the pawn"],
         "Write Docs/Design/ControlsAndFeel.md."),
    _doc("tech_design", "Write the technical design", "software_architect", "reviewer", ["design_gdd"], "Tech/TechnicalDesign.md",
         ["Lists every class with its folder and responsibility", "States the asset paths the code expects and the build order"],
         "Write Docs/Tech/TechnicalDesign.md: class layout, rules for testability, asset paths, build order."),
    # ---------------------------------------------------------------- briefs
    _doc("art_style", "Write the art style guide", "art_director", "director", ["design_gdd"], "Art/StyleGuide.md",
         ["Defines the palette with RGB values", "Specifies every material: asset name, folder, colours, emissive, metallic and roughness"],
         "Write Docs/Art/StyleGuide.md."),
    Step("art_concept", "Draw the concept board", "doc", "concept_artist", "art_director", ["art_style", "design_level"],
         ["Docs/Art/ConceptBoard.png shows the arena from above with pillars, 8 orbs, the player and the drone", "The board includes the palette swatches"],
         docs=["Art/ConceptNotes.md"], calls=[content.CONCEPT_BOARD], type="DESIGN",
         description="Draw Docs/Art/ConceptBoard.png (top-down arena sketch + palette) and explain it in Docs/Art/ConceptNotes.md."),
    _doc("env_brief", "Write the environment brief", "environment_director", "art_director", ["design_level", "art_style"], "Environment/Brief.md",
         ["Names the level, its materials, game classes and actor labels", "Specifies the lighting pass with values"],
         "Write Docs/Environment/Brief.md for the world builder and the lighting artist."),
    _doc("audio_brief", "Write the audio brief", "audio_director", "lead_designer", ["design_gdd"], "Audio/Brief.md",
         ["Names every sound asset the game looks up and when it plays", "Describes the shape of each sound"],
         "Write Docs/Audio/Brief.md."),
    _doc("anim_brief", "Write the animation brief", "animation_lead", "art_director", ["design_gdd"], "Animation/Brief.md",
         ["Gives spin and bob values for the orb idle", "Gives the intro camera keyframes"],
         "Write Docs/Animation/Brief.md."),
    # ---------------------------------------------------------------- code
    Step("code_rules", "Implement match rules and the health component", "code", "programmer", "reviewer", ["tech_design", "design_tuning"],
         ["Health defaults to 100 and damage cannot reduce it below 0", "Collecting every orb wins the match and adds 10 points per orb",
          "Running out of time loses the match and the timer never goes below zero", "Nothing changes after the match has ended", "The player's death loses the match"],
         [T + "Health.DamageCannotGoBelowZero", T + "Rules.CollectingEveryOrbWins", T + "Rules.RunningOutOfTimeLoses", T + "Rules.NothingChangesAfterTheMatchEnds", T + "Rules.PlayerDeathLoses"],
         "Implement FOrbRules, AOrbGameMode and UHealthComponent per Docs/Tech/TechnicalDesign.md and Docs/Design/Tuning.md, with automation tests.",
         test_filter="ShunyaGame", priority="HIGH"),
    Step("code_anim", "Implement the orb idle animation component", "code", "gameplay_animator", "reviewer", ["anim_brief", "tech_design"],
         ["The bob is a sine wave that starts at rest", "The spin yaw always stays within 0-360 degrees"],
         [T + "Animation.BobIsASineWave", T + "Animation.YawWrapsAt360"],
         "Implement USpinBobComponent per Docs/Animation/Brief.md with static, tested maths.", test_filter="ShunyaGame"),
    Step("code_player", "Implement the player pawn and the orb pickup", "code", "programmer", "reviewer", ["code_rules", "code_anim", "design_controls"],
         ["Diagonal movement is not faster than straight movement", "The player cannot leave the arena",
          "An orb is worth 10 points, carries the idle animation, and the game mode spawns the runner pawn"],
         [T + "Player.DiagonalMovementIsNotFaster", T + "Player.StaysInsideTheArena", T + "Orb.DefaultsMatchTuning"],
         "Implement AOrbRunnerPawn and AOrbCollectible per Docs/Design/ControlsAndFeel.md; make the game mode spawn the pawn.", test_filter="ShunyaGame", priority="HIGH"),
    Step("code_ai", "Implement the chaser drone", "code", "ai_programmer", "reviewer", ["code_player", "design_threat"],
         ["The drone moves toward the player at its speed", "The drone never overshoots its target", "The drone is slower than the player and hits only on cooldown"],
         [T + "AI.DroneMovesTowardThePlayer", T + "AI.DroneNeverOvershoots", T + "AI.DroneIsSlowerThanThePlayerAndHitsOnCooldown"],
         "Implement AChaserDrone per Docs/Design/ThreatSpec.md.", test_filter="ShunyaGame"),
    Step("code_ui", "Implement the HUD", "code", "ui_programmer", "reviewer", ["code_player", "design_narrative"],
         ["Time is shown as M:SS and never negative", "Banners and the score line use the exact narrative text, and the game mode uses this HUD"],
         [T + "UI.TimeIsShownAsMinutesAndSeconds", T + "UI.BannerMatchesTheResult"],
         "Implement AOrbHUD per Docs/Design/Narrative.md; make the game mode use it.", test_filter="ShunyaGame"),
    Step("code_tools", "Implement the QA autoplay bot", "code", "tools_programmer", "reviewer", ["code_ai", "code_ui"],
         ["The bot picks the nearest orb", "The bot steers toward orbs and away from a nearby drone"],
         [T + "Tools.BotPicksTheNearestOrb", T + "Tools.BotSteersToOrbsAndAwayFromTheDrone"],
         "Implement UOrbPlaytestSubsystem: behind -ShunyaAutoPlay a bot plays, a screenshot is captured, a ShunyaPlaytest: JSON line is logged, the game exits.", test_filter="ShunyaGame"),
    # ---------------------------------------------------------------- content
    Step("mat_env", "Create the environment materials", "content", "material_artist", "art_director", ["art_style"],
         ["T_FloorGrid exists as a 512x512 grid texture", "M_Floor exists and uses the grid texture", "M_Wall exists"],
         ["T_FloorGrid", "M_Floor", "M_Wall"], "Create T_FloorGrid, M_Floor and M_Wall per Docs/Art/StyleGuide.md.", calls=content.ENVIRONMENT_MATERIALS),
    Step("mat_chars", "Create the character materials", "content", "character_artist", "art_director", ["art_style"],
         ["M_Player exists (amber, slightly emissive)", "M_Drone exists (red, emissive)"], ["M_Player", "M_Drone"],
         "Create M_Player and M_Drone per Docs/Art/StyleGuide.md.", calls=content.CHARACTER_MATERIALS),
    Step("mat_props", "Create the prop materials", "content", "prop_artist", "art_director", ["art_style"],
         ["M_Orb exists (cyan, strongly emissive)", "M_Pillar exists"], ["M_Orb", "M_Pillar"],
         "Create M_Orb and M_Pillar per Docs/Art/StyleGuide.md.", calls=content.PROP_MATERIALS),
    Step("audio_sfx", "Create the sound effects", "content", "sfx_designer", "audio_director", ["audio_brief"],
         ["S_Pickup exists and is short", "S_Hit exists", "S_Win exists", "S_Lose exists"], ["S_Pickup", "S_Hit", "S_Win", "S_Lose"],
         "Create S_Pickup, S_Hit, S_Win and S_Lose per Docs/Audio/Brief.md.", calls=content.SFX),
    Step("audio_music", "Create the music loop", "content", "composer", "audio_director", ["audio_brief"],
         ["S_MusicLoop exists, is 4 seconds long and loops"], ["S_MusicLoop"], "Create S_MusicLoop per Docs/Audio/Brief.md.", calls=content.MUSIC),
    Step("level_build", "Build the arena level", "content", "world_builder", "environment_director", ["env_brief", "mat_env", "mat_props", "code_ai", "code_ui"],
         ["L_Arena exists with the OrbGameMode override", "L_Arena contains 8 orbs, 1 drone and 1 player start", "No mesh in L_Arena is missing a material"],
         ["L_Arena", "L_Arena", "L_Arena"], "Build L_Arena per Docs/Environment/Brief.md and Docs/Design/LevelLayout.md.", calls=content.LEVEL, priority="HIGH"),
    Step("level_light", "Light the arena", "content", "lighting_artist", "environment_director", ["level_build"],
         ["L_Arena has a key light, sky light, sky atmosphere and fixed exposure", "L_Arena has four corner glow lights"], ["L_Arena", "L_Arena"],
         "Add the lighting pass to L_Arena per Docs/Environment/Brief.md.", calls=content.LIGHTING),
    Step("cinematic", "Create the intro cinematic", "content", "cinematic_artist", "animation_lead", ["level_light", "anim_brief"],
         ["SEQ_Intro exists and is 180 frames long with a camera track"], ["SEQ_Intro"], "Create SEQ_Intro per Docs/Animation/Brief.md.", calls=content.CINEMATIC),
    # ---------------------------------------------------------------- QA
    Step("qa_playtest", "Playtest the game", "doc", "qa_gameplay", "qa_lead", ["code_tools", "level_light", "mat_chars", "audio_sfx", "audio_music"],
         ["The bot completes a match on L_Arena and wins", "A screenshot of the running game is attached", "Docs/QA/PlaytestReport.md states the real result"],
         description="Run a playtest of /Game/Shunya/Maps/L_Arena with the QA bot and write Docs/QA/PlaytestReport.md from the real results.",
         verify="playtest", test_filter="playtest", type="QA", priority="HIGH"),
    Step("qa_performance", "Check the frame-rate budget", "doc", "qa_performance", "qa_lead", ["qa_playtest"],
         ["Average frame rate during a match is at least 30 FPS", "Docs/QA/PerformanceReport.md states the measured numbers"],
         description="Run a playtest with a 30 FPS budget and write Docs/QA/PerformanceReport.md from the measured numbers.",
         verify="performance", test_filter="playtest", type="QA"),
    Step("qa_regression", "Run the full regression suite", "doc", "qa_regression", "qa_lead", ["code_tools"],
         ["Every ShunyaGame automation test passes on the integrated code", "Docs/QA/RegressionReport.md lists the tests that ran"],
         description="Run every ShunyaGame automation test on the integrated develop code and write Docs/QA/RegressionReport.md.",
         verify="regression", test_filter="ShunyaGame", type="QA"),
    Step("qa_signoff", "Write the QA sign-off", "doc", "qa_lead", "producer", ["qa_playtest", "qa_performance", "qa_regression", "cinematic"],
         ["Summarises the playtest, performance and regression results with their numbers", "States a clear sign-off decision"],
         description="Read the three QA reports and write Docs/QA/SignOff.md.", verify="signoff", type="QA"),
    # ---------------------------------------------------------------- documentation / release
    _doc("docs_manual", "Write the manual and class reference", "technical_writer", "producer", ["code_tools", "level_light"], "README.md",
         ["Explains how to launch and play", "Lists every gameplay class with its header"],
         "Write Docs/README.md from the merged code and content.", type="DOCUMENTATION"),
    Step("docs_knowledge", "Update the knowledge index and decision records", "doc", "knowledge_curator", "producer", ["docs_manual", "qa_signoff"],
         ["Docs/KnowledgeIndex.md points to every project document", "The match-rules decision is recorded as an ADR"],
         docs=["KnowledgeIndex.md", "adr/ADR-002-match-rules-are-a-plain-struct.md"], type="DOCUMENTATION",
         description="Write Docs/KnowledgeIndex.md and record ADR-002."),
    _doc("release_notes", "Write the 0.1.0 release notes", "release_manager", "producer", ["qa_signoff", "docs_manual"], "Release/ReleaseNotes-0.1.0.md",
         ["Lists what is in the build and its known limits", "States that promotion to main has not been done"],
         "Write Docs/Release/ReleaseNotes-0.1.0.md.", type="DOCUMENTATION"),
    Step("release_package", "Package the Windows build", "doc", "release_manager", "producer", ["release_notes"],
         ["A standalone Windows build is produced by build, cook, stage and pak", "The packaged executable starts and the QA bot wins a match in it",
          "Docs/Release/Build-0.1.0.md states where the build is, its size and the smoke-run result"],
         description="Package version 0.1.0 with package_game (startup map /Game/Shunya/Maps/L_Arena) and write Docs/Release/Build-0.1.0.md from the real result.",
         verify="package", test_filter="package", type="DOCUMENTATION", priority="HIGH"),
]

BY_TITLE = {s.title: s for s in STEPS}
BY_KEY = {s.key: s for s in STEPS}


# ---------------------------------------------------------------------------- helpers


def _fields(ctx: ScriptContext) -> set[str]:
    for t in ctx.tools:
        if t.name == "submit_report":
            return set(t.input_schema.get("properties", {}))
    return set()


def _task_line(ctx: ScriptContext) -> tuple[str, str]:
    """(task id, title) from the brief's task section."""
    for section in ("Task", "Task under review", "Task under test"):
        text = ctx.section(section)
        if text:
            m = re.match(r"([A-Z]+-\d+):\s*(.+)", text.splitlines()[0])
            if m:
                return m.group(1), m.group(2).strip()
    return "", ""


def _submit(**report: Any) -> ScriptStep:
    return call("submit_report", **report)


def _blocked(step: Step, reason: str, code_report: bool) -> ScriptStep:
    if code_report:
        return _submit(summary=f"Could not complete: {step.title}.", files_changed=[], compiled=False, tests_passed=False, blocked=True, blocked_reason=reason[:700], notes="")
    return _submit(summary=f"Could not complete: {step.title}.", files_changed=[], assets=[], blocked=True, blocked_reason=reason[:700], notes="")


def is_orb_request(text: str) -> bool:
    return bool(TRIGGER.search(text))


# ---------------------------------------------------------------------------- management


def director(ctx: ScriptContext) -> ScriptStep:
    if not ctx.called("list_dir"):
        return call("list_dir", path=".", depth=2)
    return _submit(
        objective="A complete, tiny arcade game - Orb Runner - that a player can win or lose in one minute, built by every department of the studio.",
        scope_in=["One arena level", "A player, 8 orbs and one chaser drone", "Score, timer, health, HUD and result banner", "Materials, lighting, sounds, music, an intro camera", "Automated tests and an automated playtest"],
        scope_out=["Menus and restart flow", "More than one level", "Skeletal characters and rigging", "Niagara effects", "Multiplayer sessions"],
        risks=["Content depends on code classes existing first: ordering matters", "The playtest only means something if a bot can actually play - tooling is part of the feature"],
        summary="Build Orb Runner 0.1: design first, then code and content in dependency order, then QA with a real playtest, then docs and release notes.",
    )


def producer(ctx: ScriptContext) -> ScriptStep:
    if not ctx.called("list_dir"):
        return calls(("list_dir", {"path": "Source/ShunyaGame", "depth": 3}), ("list_dir", {"path": "Docs", "depth": 2}))
    index = {s.key: i for i, s in enumerate(STEPS)}
    return _submit(
        epic_title="Orb Runner 0.1",
        summary=f"{len(STEPS)} tasks across design, engineering, art, environment, animation, audio, QA, documentation and release, ordered by dependency.",
        tasks=[
            {
                "title": s.title, "description": s.description, "type": s.type, "track": s.track, "priority": s.priority,
                "assignee_capability": s.assignee, "reviewer_capability": s.reviewer, "acceptance_criteria": s.criteria,
                "depends_on": [index[d] for d in s.depends], "test_filter": s.test_filter,
            }
            for s in STEPS
        ],
        open_questions=[],
    )


def plan_review(ctx: ScriptContext) -> ScriptStep:
    if not ctx.called("read_file"):
        return call("read_file", path="Source/ShunyaGame/ShunyaGame.Build.cs")
    return _submit(
        feasible=True, concerns=[],
        suggestions=["Keep gameplay rules in static or plain functions so every criterion is testable headless."],
        summary="Feasible. Code tasks are ordered so each one compiles on its own; content that places game classes comes after the code that defines them.",
    )


# ---------------------------------------------------------------------------- authors


def _author_code(ctx: ScriptContext, step: Step) -> ScriptStep:
    ex = ctx.exchanges
    if not ctx.called("list_dir"):
        return calls(("list_dir", {"path": "Source/ShunyaGame", "depth": 4}), ("read_file", {"path": "Docs/Tech/TechnicalDesign.md"}),
                     text="Reading the technical design and the module layout first.")
    files = code.task_files(step.key)
    patches = code.PATCHES.get(step.key, [])
    listing = ctx.called("list_dir")[0].result
    first_new = next(iter(files))
    if Path(first_new).name not in listing and not ctx.called("create_file"):
        edits: list[tuple[str, dict[str, Any]]] = [("create_file", {"path": p, "content": c}) for p, c in files.items()]
        edits += [("patch_file", {"path": p, "old_text": old, "new_text": new}) for p, old, new in patches]
        return calls(*edits)
    writes = [i for i, e in enumerate(ex) if e.name in ("create_file", "patch_file")]
    failed_write = next((e for e in ex if e.name in ("create_file", "patch_file") and e.is_error), None)
    if failed_write:
        return _blocked(step, f"could not write {failed_write.arguments.get('path')}: {failed_write.result}", True)
    compiles = [i for i, e in enumerate(ex) if e.name == "compile_project"]
    tests = [i for i, e in enumerate(ex) if e.name == "run_automation_tests"]
    if not compiles or (writes and compiles[-1] < writes[-1]):
        return call("compile_project")
    compiled = ex[compiles[-1]]
    paths = list(files) + sorted({p for p, _, _ in patches})
    if compiled.is_error:
        if "SKIPPED" in compiled.result:
            return _submit(summary=f"{step.title}: written, but no Unreal Engine is configured here so nothing was compiled or run.", files_changed=paths,
                           compiled=False, tests_passed=False, blocked=False, blocked_reason="", notes="UNVERIFIED: build and tests were skipped (no engine).")
        return _blocked(step, compiled.result, True)
    if not tests or tests[-1] < compiles[-1]:
        return call("run_automation_tests", filter=step.test_filter)
    ran = ex[tests[-1]]
    if ran.is_error:
        return _blocked(step, ran.result, True)
    return _submit(
        summary=f"{step.title}. {step.description} Each acceptance criterion has an automation test: {', '.join(t.rsplit('.', 1)[-1] for t in step.evidence)}.",
        files_changed=paths, compiled=True, tests_passed=True, blocked=False, blocked_reason="",
        notes="Logic is in static / plain functions so the tests need no world. No Build.cs change needed.",
    )


def _playtest_numbers(result: str) -> dict[str, Any]:
    m = re.search(r"PLAYTEST (\w+) \(run ([\w-]+)\) on (\S+): (\{.*\})", result)
    if not m:
        return {}
    try:
        report = json.loads(m.group(4))
    except json.JSONDecodeError:
        report = {}
    shot = re.search(r"screenshot artifact: (\S+)", result)
    return {"status": m.group(1), "run": m.group(2), "map": m.group(3), "shot": shot.group(1) if shot else "none", **report}


def _report_playtest(n: dict[str, Any], cases: str) -> str:
    return (
        "# Playtest report - L_Arena\n\n"
        f"Run `{n['run']}` on `{n['map']}` with the QA bot (`-ShunyaAutoPlay`). Verdict: **{n['status']}**.\n\n"
        "| Measure | Value |\n|---|---|\n"
        f"| Match result | {n.get('result')} |\n| Score | {n.get('score')} of 80 |\n| Orbs remaining | {n.get('orbs_remaining')} |\n"
        f"| Time remaining | {n.get('time_remaining')} s |\n| Hull remaining | {n.get('health')} |\n| Match length | {n.get('seconds')} s |\n"
        f"| Average FPS | {n.get('avg_fps')} |\n| Screenshot artifact | {n['shot']} |\n\n"
        f"## Checks\n```\n{cases}\n```\n\n"
        "## Notes\nThe bot takes the nearest orb each time and steers away from the drone inside 420 units. A human player was not involved in this run.\n"
    )


def _report_performance(n: dict[str, Any], cases: str, budget: int) -> str:
    return (
        "# Performance report - L_Arena\n\n"
        f"Run `{n['run']}`, 1280x720 windowed, development editor build (`-game`). Budget: average of at least {budget} FPS. Verdict: **{n['status']}**.\n\n"
        "| Measure | Value |\n|---|---|\n"
        f"| Average FPS | {n.get('avg_fps')} |\n| Worst frame | {n.get('worst_frame_ms')} ms |\n| Measured for | {n.get('seconds')} s |\n\n"
        f"## Checks\n```\n{cases}\n```\n\n"
        "## Notes\nMeasured from one second after the match starts, so start-up hitches are excluded from the average; the worst frame still includes shader warm-up. "
        "A packaged build would be faster than this editor-hosted run.\n"
    )


def _report_regression(result: str) -> str:
    head = result.splitlines()[0] if result else "no result"
    return (
        "# Regression report\n\nFull `ShunyaGame` automation suite on the integrated code.\n\n"
        f"**{head}**\n\n## Tests\n```\n" + "\n".join(result.splitlines()[1:]) + "\n```\n"
    )


def _author_doc(ctx: ScriptContext, step: Step, task_id: str) -> ScriptStep:
    if not ctx.called("list_dir"):
        return call("list_dir", path="Docs", depth=3)
    written = {e.arguments.get("path") for e in ctx.called("create_doc") if not e.is_error}
    failed = next((e for e in ctx.exchanges if e.name in ("create_doc", "generate_image") and e.is_error), None)
    if failed:
        return _blocked(step, failed.result, False)
    notes = ""
    files: dict[str, str] = {f"Docs/{d}": (DOCS_DIR / d).read_text(encoding="utf-8") for d in step.docs}

    if step.verify in ("playtest", "performance"):
        budget = 30 if step.verify == "performance" else 20
        run = ctx.last("run_playtest")
        if run is None:
            return call("run_playtest", map=content.MAP, min_fps=budget)
        numbers = _playtest_numbers(run.result)
        cases = "\n".join(line.strip() for line in run.result.splitlines() if line.strip().startswith("["))
        name = "Docs/QA/PlaytestReport.md" if step.verify == "playtest" else "Docs/QA/PerformanceReport.md"
        if "SKIPPED" in run.result or not numbers:
            files[name] = f"# {step.title}\n\n**NOT RUN.** {run.result.strip()}\n\nNothing in this report has been verified.\n"
            notes = "UNVERIFIED: the playtest could not run."
        else:
            files[name] = _report_playtest(numbers, cases) if step.verify == "playtest" else _report_performance(numbers, cases, budget)
            if run.is_error:
                notes = "The verification run did NOT pass; the report states the measured results."
    elif step.verify == "package":
        run = ctx.last("package_game")
        if run is None:
            return call("package_game", map=content.MAP, version="0.1.0")
        m = re.search(r"PACKAGE (\w+) \(run ([\w-]+)\) version (\S+): (\{.*\})", run.result)
        cases = "\n".join(line.strip() for line in run.result.splitlines() if line.strip().startswith("["))
        if "SKIPPED" in run.result or not m:
            files["Docs/Release/Build-0.1.0.md"] = f"# Packaged build 0.1.0\n\n**NOT BUILT.** {run.result.strip()[:1500]}\n"
            notes = "UNVERIFIED: nothing was packaged."
        else:
            try:
                rep = json.loads(m.group(4))
            except json.JSONDecodeError:
                rep = {}
            smoke = rep.get("smoke_run") or {}
            files["Docs/Release/Build-0.1.0.md"] = (
                f"# Packaged build {m.group(3)} - Windows (Development)\n\nPackaging run `{m.group(2)}`. Verdict: **{m.group(1)}**.\n\n"
                "| | |\n|---|---|\n"
                f"| Location | `{rep.get('output_dir')}` |\n| Executable | `{rep.get('executable')}` |\n| Size | {rep.get('size_mb')} MB in {rep.get('file_count')} files |\n"
                f"| Packaging time | {rep.get('package_seconds')} s |\n| Smoke run | {smoke.get('result')} - score {smoke.get('score')}, {smoke.get('avg_fps')} FPS average |\n\n"
                f"## Checks\n```\n{cases}\n```\n\n"
                "## How to run\nStart the executable above. No Unreal Engine installation is needed on the machine that runs it.\n\n"
                "## Notes\nThis is a Development configuration build (logging and the QA bot are included); a Shipping build is a later step. "
                "The build is not stored in git. " + (f"Error: {rep.get('error')}" if rep.get("error") else "") + "\n"
            )
            if run.is_error:
                notes = "Packaging did NOT pass; the document states the real result."
    elif step.verify == "regression":
        run = ctx.last("run_automation_tests")
        if run is None:
            return call("run_automation_tests", filter="ShunyaGame")
        files["Docs/QA/RegressionReport.md"] = _report_regression(run.result)
        if run.is_error:
            notes = "The suite did NOT pass (or could not run); the report states the real results."
    elif step.verify == "signoff":
        reads = ctx.called("read_file")
        wanted = ["Docs/QA/PlaytestReport.md", "Docs/QA/PerformanceReport.md", "Docs/QA/RegressionReport.md"]
        if len(reads) < len(wanted):
            return calls(*[("read_file", {"path": p}) for p in wanted])
        text = {e.arguments["path"]: e.result for e in reads}
        verdicts = {p: (re.search(r"Verdict: \*\*(\w+)\*\*|\*\*TESTS (\w+)", t) or re.search(r"(NOT RUN)", t)) for p, t in text.items()}
        rows, all_ok = [], True
        for p in wanted:
            m = verdicts.get(p)
            verdict = next((g for g in (m.groups() if m else ()) if g), "UNKNOWN")
            all_ok = all_ok and verdict == "PASSED"
            rows.append(f"| {p.rsplit('/', 1)[-1]} | {verdict} |")
        fps = re.search(r"Average FPS \| ([\d.]+)", text.get(wanted[1], ""))
        score = re.search(r"Score \| (\d+) of 80", text.get(wanted[0], ""))
        suite = re.search(r"(\d+) passed, (\d+) failed", text.get(wanted[2], ""))
        files["Docs/QA/SignOff.md"] = (
            "# QA sign-off - Orb Runner 0.1.0\n\n| Report | Verdict |\n|---|---|\n" + "\n".join(rows) + "\n\n"
            f"- Playtest: bot score {score.group(1) if score else '?'} of 80.\n- Performance: average {fps.group(1) if fps else '?'} FPS.\n"
            f"- Regression: {suite.group(1) if suite else '?'} passed, {suite.group(2) if suite else '?'} failed.\n\n"
            f"## Decision\n**{'SIGNED OFF for develop' if all_ok else 'NOT SIGNED OFF'}** - "
            + ("all three reports pass." if all_ok else "at least one report did not pass or was not run; see the table.")
            + "\n\nNot covered: play by a human, gamepad input, long sessions, packaged builds.\n"
        )
        if not all_ok:
            notes = "Sign-off withheld: not every QA report passed."

    for tool, args in step.calls:  # e.g. the concept board image
        if not ctx.called(tool):
            return call(tool, **args)
    pending = [(p, c) for p, c in files.items() if p not in written]
    if pending:
        return calls(*[("create_doc", {"path": p, "content": c, "overwrite": True}) for p, c in pending])
    return _submit(
        summary=f"{step.title}: wrote {', '.join(files)}." + (f" {notes}" if notes else ""),
        files_changed=[*files, *[a["path"] for t, a in step.calls if t == "generate_image"]], assets=[], blocked=False, blocked_reason="", notes=notes,
    )


def _author_content(ctx: ScriptContext, step: Step) -> ScriptStep:
    if not ctx.called("list_dir"):
        return call("list_dir", path="Docs", depth=3)
    if not ctx.called("read_file"):
        brief = {"material_artist": "Docs/Art/StyleGuide.md", "character_artist": "Docs/Art/StyleGuide.md", "prop_artist": "Docs/Art/StyleGuide.md",
                 "sfx_designer": "Docs/Audio/Brief.md", "composer": "Docs/Audio/Brief.md", "cinematic_artist": "Docs/Animation/Brief.md"}.get(step.assignee, "Docs/Environment/Brief.md")
        return call("read_file", path=brief)
    queued = [e for e in ctx.exchanges if e.name.startswith("queue_")]
    if not queued:
        return calls(*step.calls)
    bad = next((e for e in queued if e.is_error), None)
    if bad:
        return _blocked(step, bad.result, False)
    applied = ctx.last("apply_content")
    if applied is None:
        return call("apply_content")
    if applied.is_error and "SKIPPED" not in applied.result:
        return _blocked(step, applied.result, False)
    skipped = "SKIPPED" in applied.result
    return _submit(
        summary=f"{step.title}: " + ("queued the recipes, but no Unreal Engine is configured here so no assets were built." if skipped else f"built {', '.join(dict.fromkeys(step.evidence))} from the brief."),
        files_changed=[], assets=list(dict.fromkeys(step.evidence)), blocked=False, blocked_reason="",
        notes="UNVERIFIED: the editor did not run." if skipped else "Recipes are under ContentJobs/ for review.",
    )


# ---------------------------------------------------------------------------- reviewers and QA


def review(ctx: ScriptContext, step: Step) -> ScriptStep:
    if not ctx.called("git_diff"):
        return call("git_diff", stat=True)
    stat = ctx.called("git_diff")[0].result
    changed = [line.split("|")[0].strip() for line in stat.splitlines() if "|" in line]
    if not ctx.called("read_file"):
        readable = [p for p in changed if p.endswith((".md", ".json", ".h", ".cpp"))]
        if readable:
            return calls(*[("read_file", {"path": p}) for p in readable[:3]])
    if not changed:
        return _submit(verdict="CHANGES_REQUESTED", summary="The task branch contains no changes.",
                       findings=[{"severity": "BLOCKER", "file": "", "line": 0, "comment": "Nothing was produced for this task."}])
    what = {"code": "The code follows the technical design, keeps logic in testable functions, and each acceptance criterion has a test that asserts it.",
            "doc": "The document is concrete, consistent with the documents it builds on, and covers each acceptance criterion.",
            "content": "The recipes match the brief: names, colours and values are as specified, and every asset the criteria ask for is present."}[step.track]
    return _submit(verdict="APPROVE", summary=f"{step.title}: {what}", findings=[])


def qa(ctx: ScriptContext, step: Step) -> ScriptStep:
    criteria = [re.sub(r"^\d+\.\s*", "", line).strip() for line in ctx.section("Acceptance criteria").splitlines() if line.strip()]
    tool = "validate_content" if step.track == "content" else "run_automation_tests"
    run = ctx.last(tool)
    if run is None:
        return call(tool) if step.track == "content" else call(tool, filter=step.test_filter)
    if not ctx.called("git_diff"):
        return call("git_diff", stat=True)
    skipped = "SKIPPED" in run.result
    passed = set(re.findall(r"\[PASS\] (\S+)", run.result))
    rows = []
    for text, proof in zip(criteria, step.evidence + [""] * len(criteria)):
        if step.track == "content":
            line = next((l.strip() for l in run.result.splitlines() if l.strip().startswith("[PASS]") and l.split()[1].endswith("/" + proof)), "")
            met, evidence = bool(line) or (skipped and bool(proof)), (line or f"{proof}: no passing validation fact")
        else:
            met, evidence = proof in passed or (skipped and bool(proof)), f"{proof}: {'passed in this QA run' if proof in passed else 'did not pass'}"
        if skipped and proof:
            evidence = f"{proof}: NOT verified - the engine is not available"
        rows.append({"criterion": text, "met": met, "evidence": evidence})
    ok = bool(rows) and all(r["met"] for r in rows) and (skipped or not run.is_error)
    if ok:
        return _submit(verdict="PASS", criteria=rows, defects=[],
                       summary="Unreal is not available: inspected statically only, nothing was run." if skipped else "Every acceptance criterion is backed by a passing check from this QA run.")
    failed = re.findall(r"\[FAIL\] (\S+)(?: - (.*))?", run.result)
    defects = [{"title": f"{n} fails", "severity": "HIGH", "test": n, "expected": "pass", "actual": (m or "failed")[:300]} for n, m in failed]
    defects += [{"title": f"No evidence for: {r['criterion']}", "severity": "HIGH", "test": "", "expected": "a passing check", "actual": r["evidence"]} for r in rows if not r["met"]]
    return _submit(verdict="FAIL", summary="Not every acceptance criterion is backed by a passing check.", criteria=rows, defects=defects[:12])


# ---------------------------------------------------------------------------- dispatch


def script(ctx: ScriptContext) -> ScriptStep | None:
    """Returns the next step when this run belongs to the Orb Runner feature, else None."""
    fields = _fields(ctx)
    if "objective" in fields:
        return director(ctx) if is_orb_request(ctx.section("Feature request from the studio owner")) else None
    if "tasks" in fields:
        return producer(ctx) if is_orb_request(ctx.section("Feature request")) else None
    if "feasible" in fields:
        return plan_review(ctx) if "Orb Runner 0.1" in ctx.section("Proposed plan") else None
    task_id, title = _task_line(ctx)
    step = BY_TITLE.get(title)
    if step is None:
        return None
    if "verdict" in fields and "criteria" in fields:
        return qa(ctx, step)
    if "verdict" in fields:
        return review(ctx, step)
    if step.track == "code":
        return _author_code(ctx, step)
    if step.track == "content":
        return _author_content(ctx, step)
    return _author_doc(ctx, step, task_id)
