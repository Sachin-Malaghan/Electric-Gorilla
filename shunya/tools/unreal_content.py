"""Controlled Unreal content operations (spec 40, 41): asset creation, validation, promotion, playtests.

Content agents never send Python to the editor. They queue typed jobs; this service runs
the studio-owned script `unreal_scripts/apply_content.py` in a headless editor with those
jobs as data. Assets are created under /Game/AI_Staging and only move to /Game/Shunya
(production content) through `promote`, after review and validation.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from shunya.core import processes
from shunya.tools.unreal_build import _UNREAL_LOCK

SCRIPT = Path(__file__).parent / "unreal_scripts" / "apply_content.py"
# A literal statement with no spaces: UE splits -script on whitespace, and project paths may contain spaces.
BOOTSTRAP = "__import__('runpy').run_path(__import__('os').environ['SHUNYA_CONTENT_SCRIPT'],run_name='__main__')"
_PLAYTEST_LINE = re.compile(r"ShunyaPlaytest:\s*(\{.*\})")


async def run_command_line(cmdline: str, *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> tuple[int, str, bool]:
    """Run a raw Windows command line (so `-Key="value with spaces"` reaches Unreal intact)."""
    proc = subprocess.Popen(cmdline, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    processes.register(proc.pid)
    try:
        out, _ = await asyncio.to_thread(proc.communicate, None, timeout)
        processes.unregister(proc.pid)
        return proc.returncode or 0, out.decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired:
        processes.kill_tree(proc.pid)
        out, _ = await asyncio.to_thread(proc.communicate)
        return -1, out.decode("utf-8", "replace"), True
    except asyncio.CancelledError:
        processes.kill_tree(proc.pid)
        raise


def q(path: Path | str) -> str:
    return f'"{path}"'


class IContentService(ABC):
    available: bool = True

    @abstractmethod
    async def run(self, project_dir: Path, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Run one apply / validate / promote request. Returns (result, editor log)."""


class IPlaytestService(ABC):
    available: bool = True

    @abstractmethod
    async def play(self, project_dir: Path, map_path: str, timeout_s: int = 240) -> tuple[dict[str, Any], str]:
        """Launch the game with the QA bot. Returns (report incl. 'screenshot' path or None, log)."""


class UnavailableContentService(IContentService):
    available = False

    async def run(self, project_dir: Path, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        msg = "Unreal Engine is not installed/configured on this machine; no content was created or checked."
        return {"mode": request.get("mode"), "ok": False, "skipped": True, "error": msg, "results": []}, msg


class UnavailablePlaytestService(IPlaytestService):
    available = False

    async def play(self, project_dir: Path, map_path: str, timeout_s: int = 240) -> tuple[dict[str, Any], str]:
        msg = "Unreal Engine is not installed/configured on this machine; the game was NOT played."
        return {"result": "SKIPPED", "error": msg, "screenshot": None}, msg


class UnrealContentService(IContentService):
    def __init__(self, engine_root: Path, project_name: str, timeout_s: int = 900):
        self.engine_root = engine_root
        self.project_name = project_name
        self.timeout_s = timeout_s

    async def run(self, project_dir: Path, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        scratch = project_dir / "Saved" / "Shunya"
        scratch.mkdir(parents=True, exist_ok=True)
        stamp = f"{request['mode']}_{int(time.time() * 1000)}"
        request_file, result_file, log_file = scratch / f"{stamp}.request.json", scratch / f"{stamp}.result.json", scratch / f"{stamp}.log"
        request = {**request, "result": str(result_file)}
        request_file.write_text(json.dumps(request, indent=1), encoding="utf-8")
        editor = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        cmdline = (
            f"{q(editor)} {q(project_dir / (self.project_name + '.uproject'))} -run=pythonscript -script={BOOTSTRAP} "
            f"-unattended -nosplash -nopause -abslog={q(log_file)}"
        )
        env = {**os.environ, "SHUNYA_CONTENT_REQUEST": str(request_file), "SHUNYA_CONTENT_SCRIPT": str(SCRIPT)}
        async with _UNREAL_LOCK:
            code, out, timed_out = await run_command_line(cmdline, cwd=project_dir, timeout=self.timeout_s, env=env)
        log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else out
        if result_file.is_file():
            return json.loads(result_file.read_text(encoding="utf-8")), log
        reason = f"editor timed out after {self.timeout_s}s" if timed_out else f"editor exited with code {code} without writing a result"
        errors = [line.strip() for line in log.splitlines() if "Error:" in line][-8:]
        return {"mode": request["mode"], "ok": False, "error": reason, "editor_errors": errors, "results": []}, log


class UnrealPlaytestService(IPlaytestService):
    def __init__(self, engine_root: Path, project_name: str):
        self.engine_root = engine_root
        self.project_name = project_name

    async def play(self, project_dir: Path, map_path: str, timeout_s: int = 240) -> tuple[dict[str, Any], str]:
        if not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", map_path):
            return {"result": "ERROR", "error": "map must be a /Game/... package path", "screenshot": None}, ""
        scratch = project_dir / "Saved" / "Shunya"
        scratch.mkdir(parents=True, exist_ok=True)
        log_file = scratch / f"playtest_{int(time.time() * 1000)}.log"
        shots = project_dir / "Saved" / "Screenshots"
        shutil.rmtree(shots, ignore_errors=True)
        editor = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        cmdline = (
            f"{q(editor)} {q(project_dir / (self.project_name + '.uproject'))} {map_path} -game -windowed -ResX=1280 -ResY=720 "
            f"-ShunyaAutoPlay -unattended -nosplash -nosound -abslog={q(log_file)}"
        )
        async with _UNREAL_LOCK:
            code, out, timed_out = await run_command_line(cmdline, cwd=project_dir, timeout=timeout_s)
        log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else out
        match = _PLAYTEST_LINE.search(log)
        report: dict[str, Any]
        if match:
            try:
                report = json.loads(match.group(1))
            except json.JSONDecodeError:
                report = {"result": "ERROR", "error": "unreadable ShunyaPlaytest line"}
        elif timed_out:
            report = {"result": "ERROR", "error": f"the game did not finish within {timeout_s}s"}
        else:
            hint = "the map did not load, or the game has no -ShunyaAutoPlay bot that logs a 'ShunyaPlaytest:' line" if code == 0 else f"the game exited with code {code}"
            report = {"result": "ERROR", "error": f"no playtest report in the log: {hint}"}
        screenshot = next(iter(sorted(shots.rglob("Playtest*.png"))), None) if shots.is_dir() else None
        report["screenshot"] = str(screenshot) if screenshot else None
        return report, log


class IPackageService(ABC):
    available: bool = True

    @abstractmethod
    async def package(self, project_dir: Path, out_dir: Path, map_path: str) -> tuple[dict[str, Any], str]:
        """Build, cook and stage a standalone game, then smoke-run it. Returns (report, log)."""


class UnavailablePackageService(IPackageService):
    available = False

    async def package(self, project_dir: Path, out_dir: Path, map_path: str) -> tuple[dict[str, Any], str]:
        msg = "Unreal Engine is not installed/configured on this machine; nothing was packaged."
        return {"ok": False, "skipped": True, "error": msg}, msg


class UnrealPackageService(IPackageService):
    """Unreal Automation Tool `BuildCookRun`: compile the game target, cook content, stage, pak, archive."""

    def __init__(self, engine_root: Path, project_name: str, timeout_s: int = 5400):
        self.engine_root = engine_root
        self.project_name = project_name
        self.timeout_s = timeout_s

    async def package(self, project_dir: Path, out_dir: Path, map_path: str) -> tuple[dict[str, Any], str]:
        if not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", map_path):
            return {"ok": False, "error": "map must be a /Game/... package path"}, ""
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        uat = self.engine_root / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
        inner = (
            f"{q(uat)} BuildCookRun -project={q(project_dir / (self.project_name + '.uproject'))} -noP4 -platform=Win64 -clientconfig=Development "
            f"-build -cook -stage -pak -archive -archivedirectory={q(out_dir)} -map={map_path} -unattended -utf8output"
        )
        started = time.perf_counter()
        async with _UNREAL_LOCK:
            code, log, timed_out = await run_command_line(f'cmd.exe /d /s /c "{inner}"', cwd=project_dir, timeout=self.timeout_s)
        report: dict[str, Any] = {"ok": False, "package_seconds": round(time.perf_counter() - started, 1), "output_dir": str(out_dir)}
        # the launcher at the top of the build, not the inner Binaries/Win64 executable it starts
        exe = min(out_dir.rglob(f"{self.project_name}.exe"), key=lambda p: len(p.parts), default=None)
        if timed_out:
            report["error"] = f"packaging exceeded {self.timeout_s}s"
        elif code != 0 or exe is None:
            errors = [line.strip() for line in log.splitlines() if "ERROR:" in line or "Error:" in line][-6:]
            report["error"] = f"BuildCookRun exited with code {code}" + (": " + " | ".join(errors) if errors else "")
        if exe is None or "error" in report:
            return report, log
        files = [p for p in out_dir.rglob("*") if p.is_file()]
        report.update(executable=str(exe), size_mb=round(sum(p.stat().st_size for p in files) / 1_048_576, 1), file_count=len(files))

        # Smoke run: the packaged game must start and the QA bot must be able to finish a match in it.
        async with _UNREAL_LOCK:
            run_code, run_out, run_timed_out = await run_command_line(
                f"{q(exe)} {map_path} -ShunyaAutoPlay -windowed -ResX=1280 -ResY=720 -unattended -nosound -stdout -FullStdOutLogOutput", cwd=exe.parent, timeout=300)
        run_log = run_out
        for candidate in sorted(out_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
            run_log = candidate.read_text(encoding="utf-8", errors="replace")
        match = _PLAYTEST_LINE.search(run_log) or _PLAYTEST_LINE.search(run_out)
        if match:
            try:
                report["smoke_run"] = json.loads(match.group(1))
            except json.JSONDecodeError:
                report["smoke_run"] = {"result": "ERROR", "error": "unreadable ShunyaPlaytest line"}
        else:
            report["smoke_run"] = {"result": "ERROR", "error": "timed out" if run_timed_out else f"no playtest report; the packaged game exited with code {run_code}"}
        shot = next(iter(sorted(out_dir.rglob("Playtest*.png"))), None)
        report["screenshot"] = str(shot) if shot else None
        report["ok"] = report["smoke_run"].get("result") in ("WIN", "LOSE")
        return report, log + "\n\n===== packaged game smoke run =====\n" + run_log[-60_000:]


def source_fingerprint(project_dir: Path) -> str:
    """Hash of everything that affects the compiled binaries; used to know when a worktree needs a build."""
    import hashlib

    h = hashlib.sha1()
    files: list[Path] = [*project_dir.glob("*.uproject")]
    for top in ("Source", "Plugins"):
        base = project_dir / top
        if base.is_dir():
            files += [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in (".h", ".cpp", ".cs", ".uplugin", ".inl") and "Intermediate" not in p.parts and "Binaries" not in p.parts]
    for p in sorted(files):
        h.update(p.relative_to(project_dir).as_posix().encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


STAMP = Path("Saved") / "Shunya" / "build_fingerprint.txt"


def is_built(project_dir: Path) -> bool:
    stamp = project_dir / STAMP
    return stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == source_fingerprint(project_dir)


def mark_built(project_dir: Path) -> None:
    stamp = project_dir / STAMP
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(source_fingerprint(project_dir), encoding="utf-8")


def copy_binaries(src: Path, dst: Path) -> None:
    """Reuse another checkout's compiled modules when its sources are identical (saves a full compile)."""
    for rel in [Path("Binaries"), *[p.relative_to(src) for p in src.glob("Plugins/*/Binaries")]]:
        if (src / rel).is_dir():
            shutil.copytree(src / rel, dst / rel, dirs_exist_ok=True)
