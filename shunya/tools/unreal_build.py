"""Controlled Unreal build and test execution (spec 16 - Build / Testing, 17).

Agents never get a shell. They get `compile_project` and `run_automation_tests`, which run
fixed UnrealBuildTool / UnrealEditor-Cmd command lines on the task's worktree, capture the
log as an artifact, and return parsed, structured diagnostics.

When no engine is installed the services report SKIPPED - never a pass.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

from shunya.core import processes
from shunya.shared.schemas import BuildRecord, BuildStatus, CompileDiagnostic, TestCaseResult, TestRunRecord

# One UE process at a time: UnrealBuildTool holds a global mutex and the editor is heavy.
_UNREAL_LOCK = asyncio.Lock()

_MSVC = re.compile(
    r"^\s*(?P<file>(?:[A-Za-z]:)?[^:(\n]+?)\((?P<line>\d+)(?:,(?P<col>\d+))?\)\s*:\s*(?P<sev>fatal error|error|warning)\s*(?P<code>[A-Z]+\d+)?\s*:\s*(?P<msg>.+)$",
    re.I,
)
_CLANG = re.compile(r"^\s*(?P<file>(?:[A-Za-z]:)?[^:\n]+?):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>fatal error|error|warning):\s*(?P<msg>.+)$")
_LINK = re.compile(r"^\s*(?P<file>[^\s:][^:\n]*?)\s*:\s*(?P<sev>fatal error|error)\s+(?P<code>LNK\d+)\s*:\s*(?P<msg>.+)$")
_UBT = re.compile(r"^\s*(?:ERROR|Error):\s*(?P<msg>.+)$")


def parse_build_errors(log: str, *, include_warnings: bool = False, limit: int = 60) -> list[CompileDiagnostic]:
    out: list[CompileDiagnostic] = []
    seen: set[tuple] = set()
    for raw in log.splitlines():
        line = raw.rstrip()
        d: CompileDiagnostic | None = None
        if m := _MSVC.match(line):
            d = CompileDiagnostic(
                file=m["file"].strip(), line=int(m["line"]), column=int(m["col"]) if m["col"] else None,
                severity="warning" if m["sev"].lower() == "warning" else "error", code=m["code"] or "", message=m["msg"].strip(),
            )
        elif m := _LINK.match(line):
            d = CompileDiagnostic(file=m["file"].strip(), severity="error", code=m["code"], message=m["msg"].strip())
        elif m := _CLANG.match(line):
            d = CompileDiagnostic(
                file=m["file"].strip(), line=int(m["line"]), column=int(m["col"]),
                severity="warning" if m["sev"] == "warning" else "error", message=m["msg"].strip(),
            )
        elif m := _UBT.match(line):
            d = CompileDiagnostic(severity="error", code="UBT", message=m["msg"].strip())
        if d is None or (d.severity == "warning" and not include_warnings):
            continue
        key = (d.file, d.line, d.code, d.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= limit:
            break
    return out


def relativize(diags: list[CompileDiagnostic], root: Path) -> list[CompileDiagnostic]:
    root_s = str(root.resolve()).replace("\\", "/").lower()
    for d in diags:
        f = d.file.replace("\\", "/")
        if f.lower().startswith(root_s):
            d.file = f[len(root_s):].lstrip("/")
    return diags


async def _run(cmd: list[str], *, cwd: Path, timeout: int) -> tuple[int, str, bool]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    processes.register(proc.pid)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        processes.unregister(proc.pid)
        return proc.returncode or 0, out.decode("utf-8", "replace"), False
    except TimeoutError:
        processes.kill_tree(proc.pid)  # the whole tree: UnrealBuildTool's compilers, the editor's workers
        out = b""
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 10)
        except TimeoutError:
            pass
        return -1, out.decode("utf-8", "replace"), True
    except asyncio.CancelledError:
        processes.kill_tree(proc.pid)
        raise


class IBuildService(ABC):
    @abstractmethod
    async def compile(self, project_dir: Path) -> tuple[BuildRecord, str]:
        """Returns (record without ids filled, full log)."""


class ITestService(ABC):
    @abstractmethod
    async def run_tests(self, project_dir: Path, test_filter: str) -> tuple[TestRunRecord, str]: ...


class UnavailableBuildService(IBuildService):
    async def compile(self, project_dir: Path) -> tuple[BuildRecord, str]:
        msg = "Unreal Engine is not installed/configured on this machine; the project was NOT compiled."
        return BuildRecord(status=BuildStatus.SKIPPED, target="", log_tail=msg), msg


class UnavailableTestService(ITestService):
    async def run_tests(self, project_dir: Path, test_filter: str) -> tuple[TestRunRecord, str]:
        msg = "Unreal Engine is not installed/configured on this machine; tests were NOT run."
        return TestRunRecord(status="SKIPPED", filter=test_filter), msg


class UnrealBuildService(IBuildService):
    def __init__(self, engine_root: Path, project_name: str, timeout_s: int = 1800):
        self.engine_root = engine_root
        self.project_name = project_name
        self.timeout_s = timeout_s

    async def compile(self, project_dir: Path) -> tuple[BuildRecord, str]:
        uproject = project_dir / f"{self.project_name}.uproject"
        target = f"{self.project_name}Editor"
        if not uproject.is_file():
            msg = f"{uproject.name} not found in workspace"
            return BuildRecord(status=BuildStatus.ERROR, target=target, log_tail=msg), msg
        args = [
            target, "Win64", "Development", f"-project={uproject}", "-waitmutex", "-NoHotReload",
            # the installed engine caches the source file list; agents add files constantly
            "-NoUBTMakefiles",
        ]
        # Run UnrealBuildTool directly (what Build.bat does) - going through cmd.exe would
        # mangle the quoting of project paths that contain spaces.
        engine = self.engine_root / "Engine"
        dotnet = next(iter(sorted((engine / "Binaries" / "ThirdParty" / "DotNet").glob("*/win-x64/dotnet.exe"), reverse=True)), None)
        ubt = engine / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll"
        if dotnet is None or not ubt.is_file():
            msg = f"UnrealBuildTool or its bundled dotnet runtime was not found under {engine}"
            return BuildRecord(status=BuildStatus.ERROR, target=target, log_tail=msg, diagnostics=[CompileDiagnostic(code="ENV", message=msg)]), msg
        cmd = [str(dotnet), str(ubt), *args]
        started = time.perf_counter()
        async with _UNREAL_LOCK:
            code, log, timed_out = await _run(cmd, cwd=engine / "Source", timeout=self.timeout_s)
        duration = time.perf_counter() - started
        diags = relativize(parse_build_errors(log), project_dir)
        if "paths are longer than 260 characters" in log:
            # an environment problem, not something an agent can fix in code
            status = BuildStatus.ERROR
            diags = [CompileDiagnostic(code="ENV", message=(
                "Windows path limit: build output paths exceed 260 characters. Move the studio workspace "
                f"(currently {project_dir}) to a shorter path via SHUNYA_WORKSPACE_DIR."))]
        elif timed_out:
            status = BuildStatus.ERROR
            diags.append(CompileDiagnostic(code="TIMEOUT", message=f"build exceeded {self.timeout_s}s"))
        elif code == 0:
            status = BuildStatus.PASSED
            diags = []
        else:
            status = BuildStatus.FAILED
            if not diags:
                tail = "\n".join(log.splitlines()[-15:])
                diags.append(CompileDiagnostic(code="UBT", message=f"build failed with exit code {code}: {tail[-600:]}"))
        tail = "\n".join(log.splitlines()[-40:])
        return BuildRecord(status=status, target=target, duration_s=round(duration, 1), diagnostics=diags, log_tail=tail), log


_LOG_RESULT = re.compile(r"Test Completed\. Result=\{(?P<res>\w+)\} Name=\{(?P<name>[^}]*)\} Path=\{(?P<path>[^}]*)\}")


def parse_automation_report(report_dir: Path, log: str) -> list[TestCaseResult]:
    index = report_dir / "index.json"
    results: list[TestCaseResult] = []
    if index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8-sig"))
            for t in data.get("tests", []):
                state = str(t.get("state", ""))
                msgs = [
                    str(e.get("event", {}).get("message", ""))
                    for e in t.get("entries", [])
                    if str(e.get("event", {}).get("type", "")).lower() in ("error", "warning")
                ]
                results.append(
                    TestCaseResult(
                        name=t.get("fullTestPath") or t.get("testDisplayName", "?"),
                        result="PASS" if state == "Success" else ("SKIPPED" if state in ("NotRun", "Skipped") else "FAIL"),
                        duration_s=float(t.get("duration", 0) or 0),
                        messages=[m for m in msgs if m][:8],
                    )
                )
        except (json.JSONDecodeError, OSError):
            results = []
    if not results:
        for m in _LOG_RESULT.finditer(log):
            results.append(TestCaseResult(name=m["path"] or m["name"], result="PASS" if m["res"] in ("Success", "Passed") else "FAIL"))
    return results


class UnrealTestService(ITestService):
    def __init__(self, engine_root: Path, project_name: str, scratch_dir: Path, timeout_s: int = 1200):
        self.engine_root = engine_root
        self.project_name = project_name
        self.scratch_dir = scratch_dir
        self.timeout_s = timeout_s

    async def run_tests(self, project_dir: Path, test_filter: str) -> tuple[TestRunRecord, str]:
        if not re.fullmatch(r"[A-Za-z0-9_.]+", test_filter):
            msg = "test filter may only contain letters, digits, '.' and '_'"
            return TestRunRecord(status="ERROR", filter=test_filter), msg
        uproject = project_dir / f"{self.project_name}.uproject"
        editor = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        stamp = f"{int(time.time() * 1000)}"
        report_dir = self.scratch_dir / f"report_{stamp}"
        report_dir.mkdir(parents=True, exist_ok=True)
        log_path = report_dir / "Tests.log"
        cmd = [
            str(editor), str(uproject),
            f"-ExecCmds=Automation RunTests {test_filter}; Quit",
            "-TestExit=Automation Test Queue Empty",
            f"-ReportExportPath={report_dir}",
            f"-abslog={log_path}",
            "-nullrhi", "-unattended", "-nosplash", "-nopause", "-nosound", "-stdout",
        ]
        started = time.perf_counter()
        async with _UNREAL_LOCK:
            code, out, timed_out = await _run(cmd, cwd=project_dir, timeout=self.timeout_s)
        duration = time.perf_counter() - started
        log = out
        if log_path.is_file():
            log = log_path.read_text(encoding="utf-8", errors="replace")
        results = parse_automation_report(report_dir, log)
        passed = sum(1 for r in results if r.result == "PASS")
        failed = sum(1 for r in results if r.result == "FAIL")
        if timed_out:
            status = "ERROR"
            results.append(TestCaseResult(name="(runner)", result="FAIL", messages=[f"test run exceeded {self.timeout_s}s"]))
        elif not results:
            status = "ERROR"
            hint = "no tests matched the filter" if "No automation tests matched" in log or code == 0 else f"editor exited with code {code}"
            results.append(TestCaseResult(name="(runner)", result="FAIL", messages=[hint]))
        else:
            status = "PASSED" if failed == 0 and passed > 0 else "FAILED"
        rec = TestRunRecord(status=status, filter=test_filter, passed=passed, failed=failed, results=results, duration_s=round(duration, 1))
        return rec, log
