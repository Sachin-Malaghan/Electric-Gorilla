"""Content tools for art, environment, animation, audio and QA agents (spec 16 - Assets, 40, 41).

An agent queues typed jobs (they are saved as JSON under ContentJobs/<task>/ in its
worktree, so every asset has a reviewable, reproducible recipe), then calls
`apply_content` once: a single headless editor session creates everything under
/Game/AI_Staging. `validate_content` loads assets and reports facts. Promotion to
production content is done by the orchestrator, never by an agent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from shunya.shared.schemas import AgentState, ArtifactType, TestCaseResult, TestRunRecord
from shunya.tools.base import Tool, ToolContext, ToolError, ToolResult
from shunya.tools.content import generators as gen

NAME = r"^[A-Za-z][A-Za-z0-9_]{1,47}$"
FOLDER = r"^[A-Za-z][A-Za-z0-9_]{1,31}$"
Vec3 = list[float]


def _jobs_dir(ctx: ToolContext, *, for_write: bool = False) -> Path:
    sb = ctx.require_sandbox()
    task = ctx.task.id if ctx.task else "adhoc"
    return sb.resolve(f"ContentJobs/{task}", for_write=for_write)


def _queue(ctx: ToolContext, job: dict[str, Any]) -> str:
    folder = _jobs_dir(ctx, for_write=True)
    folder.mkdir(parents=True, exist_ok=True)
    name = job.get("name") or job.get("level")
    suffix = f"_{job['kind']}_{name}.json"
    existing = next((p for p in folder.glob("*.json") if p.name.endswith(suffix)), None)
    # queueing the same asset again replaces its recipe (a correction), it never duplicates the job
    path = existing or folder / f"{len(list(folder.glob('*.json'))) + 1:02d}{suffix}"
    path.write_text(json.dumps(job, indent=2), encoding="utf-8", newline="\n")
    return ctx.require_sandbox().relative(path)


def _queued(ctx: ToolContext) -> list[dict[str, Any]]:
    folder = _jobs_dir(ctx)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))] if folder.is_dir() else []


class _Named(BaseModel):
    name: str = Field(pattern=NAME, description="Asset name, e.g. M_Floor")
    folder: str = Field(pattern=FOLDER, description="Content sub-folder, e.g. Environment, Characters, Props, Audio, Maps")


def _color(v: Vec3) -> Vec3:
    if len(v) != 3 or any(c < 0 or c > 1 for c in v):
        raise ValueError("colour must be [r, g, b] with components in 0..1")
    return v


class QueueTexture(Tool):
    name = "queue_texture"
    description = "Queue a procedural tiling texture (grid, checker, noise, gradient or solid). Generates the PNG source and queues its import."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(_Named):
        pattern: Literal["grid", "checker", "noise", "gradient", "solid"]
        color_a: Vec3 = Field(description="[r, g, b] 0..1 - background")
        color_b: Vec3 = Field(description="[r, g, b] 0..1 - lines / second colour")
        size: Literal[64, 128, 256, 512, 1024] = 512
        cells: int = Field(default=8, ge=1, le=64)

        _c = field_validator("color_a", "color_b")(_color)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        source = sb.resolve(f"SourceArt/Generated/{args.name}.png", for_write=True)
        gen.generate_texture(source, pattern=args.pattern, size=args.size, color_a=gen.color8(args.color_a), color_b=gen.color8(args.color_b), cells=args.cells)
        rel = _queue(ctx, {"kind": "texture", "name": args.name, "folder": args.folder, "source": sb.relative(source), "srgb": True})
        return ToolResult(content=f"Generated {sb.relative(source)} ({args.size}x{args.size} {args.pattern}) and queued {rel}", summary=f"Queued texture {args.name}", files_written=[sb.relative(source), rel])


class QueueMaterial(Tool):
    name = "queue_material"
    description = "Queue a surface material: base colour, optional emissive glow, metallic, roughness, optional texture (by asset name) multiplied into the colour."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(_Named):
        base_color: Vec3
        emissive_color: Vec3 | None = None
        emissive_strength: float = Field(default=0.0, ge=0, le=200)
        metallic: float = Field(default=0.0, ge=0, le=1)
        roughness: float = Field(default=0.6, ge=0, le=1)
        texture: str | None = Field(default=None, pattern=NAME, description="Name of a texture asset (queued earlier or already in the project)")
        uv_tiling: float = Field(default=1.0, gt=0, le=256)

        _c = field_validator("base_color")(_color)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        rel = _queue(ctx, {"kind": "material", **args.model_dump()})
        return ToolResult(content=f"Queued material {args.name} ({rel})", summary=f"Queued material {args.name}", files_written=[rel])


class Note(BaseModel):
    frequency: float = Field(ge=0, le=12000, description="Hz; 0 is a rest")
    duration: float = Field(gt=0, le=4, description="seconds")
    waveform: Literal["sine", "square", "triangle", "saw", "noise"] = "sine"
    volume: float = Field(default=0.6, ge=0, le=1)
    decay: float = Field(default=0.5, ge=0, le=1)
    slide_to: float | None = Field(default=None, ge=0, le=12000)


class QueueSound(Tool):
    name = "queue_sound"
    description = "Queue a synthesised sound: a sequence of notes (frequency, duration, waveform, volume, decay, optional pitch slide). Generates the WAV and queues its import."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(_Named):
        notes: list[Note] = Field(min_length=1, max_length=256)
        looping: bool = False

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        source = sb.resolve(f"SourceArt/Generated/{args.name}.wav", for_write=True)
        seconds = gen.generate_sound(source, notes=[n.model_dump() for n in args.notes])
        rel = _queue(ctx, {"kind": "sound", "name": args.name, "folder": args.folder, "source": sb.relative(source), "looping": args.looping})
        return ToolResult(content=f"Synthesised {sb.relative(source)} ({seconds:.2f}s, {len(args.notes)} notes) and queued {rel}", summary=f"Queued sound {args.name}", files_written=[sb.relative(source), rel])


class ActorSpec(BaseModel):
    type: Literal["static_mesh", "actor_class", "player_start", "directional_light", "point_light", "sky_light", "sky_atmosphere", "exponential_height_fog", "post_process"]
    label: str = Field(pattern=r"^[A-Za-z0-9_ ]{1,48}$")
    location: Vec3 = [0.0, 0.0, 0.0]
    rotation: Vec3 = Field(default=[0.0, 0.0, 0.0], description="[pitch, yaw, roll] degrees")
    scale: Vec3 | None = None
    shape: Literal["Cube", "Sphere", "Cylinder", "Cone", "Plane"] | None = Field(default=None, description="static_mesh only (100 cm basic shapes)")
    material: str | None = Field(default=None, pattern=NAME, description="static_mesh only: material asset name")
    class_path: str | None = Field(default=None, pattern=r"^/Script/[A-Za-z0-9_]+\.[A-Za-z0-9_]+$", description="actor_class only, e.g. /Script/ShunyaGame.OrbCollectible")
    intensity: float | None = None
    color: Vec3 | None = None
    radius: float | None = None
    exposure_brightness: float | None = None


class QueueLevel(Tool):
    name = "queue_level"
    description = "Queue a new level built from a list of actors (basic-shape meshes with materials, game classes, player start, lights). Replaces the level if it already exists in staging."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(_Named):
        game_mode: str | None = Field(default=None, pattern=r"^/Script/[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
        actors: list[ActorSpec] = Field(min_length=1, max_length=400)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        rel = _queue(ctx, {"kind": "level", **args.model_dump(exclude_none=True)})
        return ToolResult(content=f"Queued level {args.name} with {len(args.actors)} actors ({rel})", summary=f"Queued level {args.name}", files_written=[rel])


class QueueLevelAdditions(Tool):
    name = "queue_level_additions"
    description = "Queue actors to add to an existing level (e.g. a lighting pass). Actors with the same label are replaced, so the job can be re-run."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(BaseModel):
        level: str = Field(pattern=NAME, description="Existing level asset name, e.g. L_Arena")
        actors: list[ActorSpec] = Field(min_length=1, max_length=200)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        rel = _queue(ctx, {"kind": "level_additions", **args.model_dump(exclude_none=True)})
        return ToolResult(content=f"Queued {len(args.actors)} additions to {args.level} ({rel})", summary=f"Queued additions to {args.level}", files_written=[rel])


class CameraKey(BaseModel):
    time: float = Field(ge=0, le=120)
    location: Vec3
    rotation: Vec3 = Field(description="[pitch, yaw, roll] degrees")


class QueueSequence(Tool):
    name = "queue_sequence"
    description = "Queue a cinematic Level Sequence: one camera that moves through keyframes, with a camera cut for the whole duration."
    required_permissions = ["write_content"]
    activity = AgentState.CODING

    class Input(_Named):
        duration_seconds: float = Field(gt=0, le=120)
        fps: Literal[24, 30, 60] = 30
        camera_keys: list[CameraKey] = Field(min_length=2, max_length=64)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        rel = _queue(ctx, {"kind": "sequence", **args.model_dump()})
        return ToolResult(content=f"Queued sequence {args.name} ({rel})", summary=f"Queued sequence {args.name}", files_written=[rel])


class _Empty(BaseModel):
    pass


def _result_lines(result: dict[str, Any]) -> list[str]:
    lines = []
    for r in result.get("results", []):
        if r.get("ok"):
            lines.append(f"  [OK]   {r.get('kind', '')} {r.get('name') or r.get('path')}: {r.get('detail') or r.get('asset_class') or r.get('path')}")
        else:
            lines.append(f"  [FAIL] {r.get('kind', '')} {r.get('name') or r.get('path')}: {r.get('error')}")
    if result.get("error"):
        lines.append(f"  editor: {result['error']} {' | '.join(result.get('editor_errors', []))}")
    return lines


class ApplyContent(Tool):
    name = "apply_content"
    description = (
        "Run every job you queued in one headless Unreal Editor session. Assets are created under /Game/AI_Staging. "
        "Returns OK/FAIL per job. Takes a minute or two - queue everything first, then call this once."
    )
    required_permissions = ["write_content"]
    activity = AgentState.COMPILING

    Input = _Empty

    def describe_call(self, args: BaseModel) -> str:
        return "Building assets in the Unreal Editor"

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        sb = ctx.require_sandbox()
        jobs = _queued(ctx)
        if not jobs:
            raise ToolError("no jobs are queued; use the queue_* tools first")
        await ctx.services.ensure_built(sb.root, task_id=ctx.task.id if ctx.task else None, agent_id=ctx.agent.id, trace_id=ctx.run.trace_id)
        result, log = await ctx.services.content.run(sb.root, {"mode": "apply", "jobs": jobs})
        ctx.services.artifacts.put(type=ArtifactType.BUILD_LOG, title=f"Content apply log ({ctx.agent.id})", creator=ctx.agent.id, content=log, task_id=ctx.task.id if ctx.task else None)
        ok = bool(result.get("ok"))
        head = "CONTENT APPLIED" if ok else ("CONTENT SKIPPED (no engine)" if result.get("skipped") else "CONTENT FAILED")
        return ToolResult(
            ok=ok, content="\n".join([f"{head}: {sum(1 for r in result.get('results', []) if r.get('ok'))}/{len(jobs)} jobs", *_result_lines(result)]),
            summary=f"Applied content: {'ok' if ok else 'failed'} ({len(jobs)} jobs)", data={"result": result, "errors": [{"code": "CONTENT", "file": r.get("name", ""), "message": r.get("error", "")} for r in result.get("results", []) if not r.get("ok")]},
        )


class ValidateContent(Tool):
    name = "validate_content"
    description = (
        "Load this task's staged assets in a headless editor and report facts: class, size on disk, texture size, sound duration, "
        "level actor counts / game mode / meshes without materials, sequence length. A validation run is recorded as evidence."
    )
    required_permissions = ["run_tests"]
    activity = AgentState.TESTING

    Input = _Empty

    def describe_call(self, args: BaseModel) -> str:
        return "Validating assets in the Unreal Editor"

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        sb = ctx.require_sandbox()
        task_id = ctx.task.id if ctx.task else None
        await ctx.services.ensure_built(sb.root, task_id=task_id, agent_id=ctx.agent.id, trace_id=ctx.run.trace_id)
        jobs = _queued(ctx)
        levels = [j["level"] for j in jobs if j["kind"] == "level_additions"]
        result, log = await ctx.services.content.run(sb.root, {"mode": "validate", "roots": ["/Game/AI_Staging"], "assets": [], "names": levels})
        facts = result.get("results", [])
        expected = {j["name"] for j in jobs if j.get("name")}
        found = {Path(f["path"]).name for f in facts}
        cases = [TestCaseResult(name=f"Content.{Path(f['path']).name}.LoadsAndIsValid", result="PASS" if f.get("ok") else "FAIL", messages=[json.dumps({k: v for k, v in f.items() if k not in ('path', 'ok')})[:400]]) for f in facts]
        cases += [TestCaseResult(name=f"Content.{name}.Exists", result="FAIL", messages=["queued but not present in /Game/AI_Staging"]) for name in sorted(expected - found)]
        passed, failed = sum(1 for c in cases if c.result == "PASS"), sum(1 for c in cases if c.result == "FAIL")
        status = "SKIPPED" if result.get("skipped") else ("PASSED" if failed == 0 and passed > 0 and not result.get("error") else "FAILED")
        log_art = ctx.services.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"Content validation ({ctx.agent.id})", creator=ctx.agent.id, content=json.dumps(result, indent=1), task_id=task_id, content_type="application/json")
        record = await ctx.services.record_test_run(TestRunRecord(task_id=task_id, filter="content", status=status, passed=passed, failed=failed, results=cases, log_artifact_id=log_art.id), agent_id=ctx.agent.id, trace_id=ctx.run.trace_id)
        lines = [f"VALIDATION {status} (run {record.id}): {passed} valid, {failed} invalid"]
        for f in facts:
            detail = {k: v for k, v in f.items() if k not in ("path", "ok", "labels")}
            lines.append(f"  [{'PASS' if f.get('ok') else 'FAIL'}] {f['path']} {json.dumps(detail)}")
        lines += [f"  [FAIL] {name}: queued but missing" for name in sorted(expected - found)]
        if result.get("error"):
            lines.append(f"  editor: {result['error']}")
        return ToolResult(ok=status == "PASSED", content="\n".join(lines), summary=f"Content validation {status} ({passed}/{passed + failed})", data={"test_run_id": record.id, "status": status, "facts": facts})


class GenerateImage(Tool):
    name = "generate_image"
    description = "Draw a simple PNG board from rectangles and circles (concept boards, palettes, layout sketches) into Docs/. No editor needed."
    required_permissions = ["write_docs"]
    activity = AgentState.CODING

    class Shape(BaseModel):
        shape: Literal["rect", "circle"]
        color: Vec3
        x: int
        y: int
        w: int = 0
        h: int = 0
        r: int = 0

    class Input(BaseModel):
        path: str = Field(pattern=r"^Docs/[A-Za-z0-9_/]+\.png$")
        width: int = Field(default=960, ge=64, le=2048)
        height: int = Field(default=540, ge=64, le=2048)
        background: Vec3 = [0.06, 0.07, 0.1]
        shapes: list["GenerateImage.Shape"] = Field(min_length=1, max_length=400)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        target = sb.resolve(args.path, for_write=True)
        gen.generate_image(target, width=args.width, height=args.height, background=gen.color8(args.background), shapes=[s.model_dump() for s in args.shapes])
        rel = sb.relative(target)
        return ToolResult(content=f"Wrote {rel} ({args.width}x{args.height}, {len(args.shapes)} shapes)", summary=f"Drew {rel}", files_written=[rel])


GenerateImage.Input.model_rebuild()


class RunPlaytest(Tool):
    name = "run_playtest"
    description = (
        "Launch the real game on a map with the QA bot playing (-ShunyaAutoPlay). Returns the match result, score, time, "
        "average FPS and worst frame, and captures a screenshot as evidence. Takes a few minutes."
    )
    required_permissions = ["run_tests", "unreal_runtime"]
    activity = AgentState.TESTING

    class Input(BaseModel):
        map: str = Field(pattern=r"^/Game/[A-Za-z0-9_/]+$", description="e.g. /Game/Shunya/Maps/L_Arena")
        min_fps: float = Field(default=20.0, ge=1, le=240, description="Performance budget: average FPS must be at least this")

    def describe_call(self, args: BaseModel) -> str:
        return f"Playtesting {getattr(args, 'map', '')}"

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        task_id = ctx.task.id if ctx.task else None
        await ctx.services.ensure_built(sb.root, task_id=task_id, agent_id=ctx.agent.id, trace_id=ctx.run.trace_id)
        report, log = await ctx.services.playtest.play(sb.root, args.map)
        log_art = ctx.services.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"Playtest log {args.map}", creator=ctx.agent.id, content=log[-200_000:], task_id=task_id)
        shot_id = None
        if report.get("screenshot") and Path(report["screenshot"]).is_file():
            shot = ctx.services.artifacts.put(type=ArtifactType.TEST_REPORT, title=f"Playtest screenshot {args.map}", creator=ctx.agent.id, content=Path(report["screenshot"]).read_bytes(), task_id=task_id, content_type="image/png")
            shot_id = shot.id
        result = str(report.get("result", "ERROR"))
        name = re.sub(r"[^A-Za-z0-9]", "_", args.map.rsplit("/", 1)[-1])
        cases: list[TestCaseResult] = []
        if result == "SKIPPED":
            status = "SKIPPED"
        else:
            fps = float(report.get("avg_fps", 0.0))
            cases = [
                TestCaseResult(name=f"Playtest.{name}.BotCompletesTheMatch", result="PASS" if result in ("WIN", "LOSE") else "FAIL", messages=[f"result={result} {report.get('error', '')}".strip()]),
                TestCaseResult(name=f"Playtest.{name}.BotWins", result="PASS" if result == "WIN" else "FAIL", messages=[f"score={report.get('score')} orbs_remaining={report.get('orbs_remaining')} health={report.get('health')}"]),
                TestCaseResult(name=f"Playtest.{name}.AverageFpsAtLeast{int(args.min_fps)}", result="PASS" if fps >= args.min_fps else "FAIL", messages=[f"avg_fps={fps} worst_frame_ms={report.get('worst_frame_ms')}"]),
                TestCaseResult(name=f"Playtest.{name}.ScreenshotCaptured", result="PASS" if shot_id else "FAIL", messages=[f"artifact={shot_id}"]),
            ]
            if "missing_content" in report:
                cases.append(TestCaseResult(name=f"Playtest.{name}.AllRuntimeContentPresent", result="PASS" if report["missing_content"] == 0 else "FAIL", messages=[f"missing_content={report['missing_content']}"]))
            status = "PASSED" if all(c.result == "PASS" for c in cases) else "FAILED"
        record = await ctx.services.record_test_run(
            TestRunRecord(task_id=task_id, filter=f"playtest:{args.map}", status=status, passed=sum(c.result == "PASS" for c in cases), failed=sum(c.result == "FAIL" for c in cases), results=cases, log_artifact_id=log_art.id),
            agent_id=ctx.agent.id, trace_id=ctx.run.trace_id,
        )
        public = {k: v for k, v in report.items() if k != "screenshot"}
        lines = [f"PLAYTEST {status} (run {record.id}) on {args.map}: {json.dumps(public)}", f"  screenshot artifact: {shot_id or 'none'}"]
        lines += [f"  [{c.result}] {c.name} - {'; '.join(c.messages)}" for c in cases]
        return ToolResult(ok=status == "PASSED", content="\n".join(lines), summary=f"Playtest {status}: {result}", data={"test_run_id": record.id, "status": status, "report": public, "screenshot_artifact_id": shot_id})


class PackageGame(Tool):
    name = "package_game"
    description = (
        "Package the game into a standalone Windows build (compile the game target, cook, stage, pak) and smoke-run the packaged "
        "executable with the QA bot. Takes a long time (tens of minutes). The build is written outside the repository; the result is recorded as evidence."
    )
    required_permissions = ["package"]
    activity = AgentState.COMPILING

    class Input(BaseModel):
        map: str = Field(pattern=r"^/Game/[A-Za-z0-9_/]+$", description="Startup map, e.g. /Game/Shunya/Maps/L_Arena")
        version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", description="e.g. 0.1.0")

    def describe_call(self, args: BaseModel) -> str:
        return f"Packaging build {getattr(args, 'version', '')}"

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        task_id = ctx.task.id if ctx.task else None
        await ctx.services.ensure_built(sb.root, task_id=task_id, agent_id=ctx.agent.id, trace_id=ctx.run.trace_id)
        out_dir = ctx.services.settings.builds_dir / f"v{args.version}"
        report, log = await ctx.services.packager.package(sb.root, out_dir, args.map)
        log_art = ctx.services.artifacts.put(type=ArtifactType.BUILD_LOG, title=f"Packaging log {args.version}", creator=ctx.agent.id, content=log[-400_000:], task_id=task_id)
        shot_id = None
        if report.get("screenshot") and Path(report["screenshot"]).is_file():
            shot_id = ctx.services.artifacts.put(type=ArtifactType.BUILD_ARTIFACT, title=f"Packaged build {args.version} screenshot", creator=ctx.agent.id,
                                                 content=Path(report["screenshot"]).read_bytes(), task_id=task_id, content_type="image/png").id
        smoke = report.get("smoke_run") or {}
        cases: list[TestCaseResult] = []
        if report.get("skipped"):
            status = "SKIPPED"
        else:
            cases = [
                TestCaseResult(name="Package.BuildCookStageSucceeded", result="PASS" if report.get("executable") else "FAIL", messages=[str(report.get("error") or f"{report.get('size_mb')} MB in {report.get('file_count')} files")]),
                TestCaseResult(name="Package.ExecutableStartsAndBotFinishesAMatch", result="PASS" if smoke.get("result") in ("WIN", "LOSE") else "FAIL", messages=[json.dumps(smoke)[:300]]),
                TestCaseResult(name="Package.BotWinsInThePackagedGame", result="PASS" if smoke.get("result") == "WIN" else "FAIL", messages=[f"score={smoke.get('score')} avg_fps={smoke.get('avg_fps')}"]),
            ]
            if "missing_content" in smoke:  # content the code loads by path is not referenced by the map, so the cooker can silently leave it out
                cases.append(TestCaseResult(name="Package.AllRuntimeContentIsInTheBuild", result="PASS" if smoke["missing_content"] == 0 else "FAIL", messages=[f"missing_content={smoke['missing_content']}"]))
            status = "PASSED" if all(c.result == "PASS" for c in cases) else "FAILED"
        record = await ctx.services.record_test_run(
            TestRunRecord(task_id=task_id, filter="package", status=status, passed=sum(c.result == "PASS" for c in cases), failed=sum(c.result == "FAIL" for c in cases), results=cases, log_artifact_id=log_art.id),
            agent_id=ctx.agent.id, trace_id=ctx.run.trace_id,
        )
        public = {k: v for k, v in report.items() if k != "screenshot"}
        lines = [f"PACKAGE {status} (run {record.id}) version {args.version}: {json.dumps(public)}", f"  screenshot artifact: {shot_id or 'none'}"]
        lines += [f"  [{c.result}] {c.name} - {'; '.join(c.messages)}" for c in cases]
        return ToolResult(ok=status == "PASSED", content="\n".join(lines), summary=f"Package {status}", data={"test_run_id": record.id, "status": status, "report": public})


CONTENT_TOOLS = [QueueTexture, QueueMaterial, QueueSound, QueueLevel, QueueLevelAdditions, QueueSequence, ApplyContent, ValidateContent, GenerateImage, RunPlaytest, PackageGame]
