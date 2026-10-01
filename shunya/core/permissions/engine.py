"""Capability-based authorization and sandboxed path validation (spec 27, 29, 30).

The LLM is not the authorization layer: every tool call passes through PermissionEngine
and every path through WorkspaceSandbox, both plain deterministic code.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from shunya.core.interfaces import ISandbox
from shunya.shared.schemas import AgentProfile, PermissionLevel

# Capability names used by tools' required_permissions.
CAPABILITIES = {
    "read_docs",
    "write_docs",
    "read_code",
    "write_code",
    "compile",
    "run_tests",
    "git_read",
    "git_commit",
    "merge",
    "deploy",
    "unreal_read",
    "unreal_editor_modify",
    "unreal_runtime",
    "knowledge_search",
    "package",
}

# Never writable by an agent, even inside its own worktree: these are project
# configuration / dependency changes that require a human approval (spec 28).
DEFAULT_PROTECTED_GLOBS = [
    ".git",
    ".git/*",
    "*.uproject",
    "*.uplugin",
    "*.Build.cs",
    "*.Target.cs",
    "Config/*",
    "Binaries/*",
    "Intermediate/*",
    "Saved/*",
    "DerivedDataCache/*",
]


class PermissionDenied(Exception):
    pass


class PathViolation(PermissionDenied):
    pass


@dataclass
class Decision:
    allowed: bool
    needs_approval: bool = False
    reason: str = ""


class PermissionEngine:
    def check(self, profile: AgentProfile, tool_name: str, required: list[str], *, isolated_workspace: bool) -> Decision:
        if tool_name not in profile.tools:
            return Decision(False, reason=f"tool '{tool_name}' is not granted to {profile.id}")
        for perm in required:
            level = profile.permissions.get(perm, PermissionLevel.NO)
            if level == PermissionLevel.YES:
                continue
            if level == PermissionLevel.CONDITIONAL:
                if isolated_workspace:
                    continue
                return Decision(False, reason=f"'{perm}' is only allowed inside an isolated task workspace")
            if level == PermissionLevel.APPROVAL:
                return Decision(False, needs_approval=True, reason=f"'{perm}' requires human approval")
            return Decision(False, reason=f"{profile.id} lacks permission '{perm}'")
        return Decision(True)

    def require(self, profile: AgentProfile, tool_name: str, required: list[str], *, isolated_workspace: bool) -> None:
        d = self.check(profile, tool_name, required, isolated_workspace=isolated_workspace)
        if not d.allowed:
            raise PermissionDenied(d.reason)


def _match(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel.lower(), p.lower()) for p in patterns)


class WorkspaceSandbox(ISandbox):
    """An agent's working copy. Reads anywhere inside it; writes only to allowed globs."""

    def __init__(
        self,
        root: Path,
        *,
        writable_globs: list[str] | None = None,
        protected_globs: list[str] | None = None,
        isolated: bool = True,
        max_file_bytes: int = 512_000,
    ):
        self.root = root.resolve()
        self.writable_globs = writable_globs or []
        self.protected_globs = protected_globs if protected_globs is not None else list(DEFAULT_PROTECTED_GLOBS)
        self.isolated = isolated
        self.max_file_bytes = max_file_bytes

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def resolve(self, relative_path: str, *, for_write: bool = False) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise PathViolation("path must be a non-empty string")
        raw = relative_path.strip().replace("\\", "/")
        if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
            raise PathViolation(f"absolute paths are not allowed: {relative_path}")
        if "\x00" in raw:
            raise PathViolation("invalid path")
        candidate = (self.root / PurePosixPath(raw)).resolve()
        try:
            rel = candidate.relative_to(self.root).as_posix()
        except ValueError:
            raise PathViolation(f"path escapes the workspace: {relative_path}") from None
        if rel in ("", "."):
            if for_write:
                raise PathViolation("cannot write the workspace root")
            return candidate
        if rel == ".git" or rel.startswith(".git/"):
            raise PathViolation("the .git directory is not accessible to agents")
        if for_write:
            if not self.isolated:
                raise PathViolation("writes are only allowed inside an isolated task worktree")
            if _match(rel, self.protected_globs):
                raise PathViolation(
                    f"'{rel}' is protected (project configuration / dependencies / build output); "
                    "changing it requires human approval - describe the needed change in your report instead"
                )
            if not _match(rel, self.writable_globs):
                raise PathViolation(f"'{rel}' is outside your writable areas: {', '.join(self.writable_globs) or 'none'}")
        return candidate
