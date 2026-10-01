"""Git isolation (spec 19): every task gets its own branch + worktree off `develop`.

Agents never touch `main`; merges go into `develop` only, and only after a human approval
(the orchestrator calls GitService.merge_to_develop - no agent has a merge tool).
"""

from __future__ import annotations

import asyncio
import fnmatch
import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from shunya.core.permissions import DEFAULT_PROTECTED_GLOBS
from shunya.shared.schemas import AgentState
from shunya.tools.base import Tool, ToolContext, ToolResult

DEVELOP = "develop"
MAIN = "main"
BOT = ["-c", "user.name=Shunya Studio", "-c", "user.email=studio@shunya.local", "-c", "core.autocrlf=false"]


class GitError(Exception):
    pass


@dataclass
class GitResult:
    code: int
    out: str
    err: str


async def git(cwd: Path, *args: str, check: bool = True, timeout: float = 120) -> GitResult:
    proc = await asyncio.create_subprocess_exec(
        "git", *BOT, *args, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        raise GitError(f"git {' '.join(args)} timed out") from None
    res = GitResult(proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))
    if check and res.code != 0:
        raise GitError(f"git {' '.join(args)} failed ({res.code}): {res.err.strip() or res.out.strip()}")
    return res


class GitService:
    def __init__(self, repo: Path, worktrees_dir: Path):
        self.repo = repo
        self.worktrees_dir = worktrees_dir
        # operations on the shared repository (worktree add/remove, merges) must not interleave
        self._repo_lock = asyncio.Lock()

    async def ensure_repo(self, template: Path | None = None) -> None:
        """Create the game repository from the template on first run (main + develop)."""
        if (self.repo / ".git").exists():
            return
        if template is None or not template.is_dir():
            raise GitError(f"game repo {self.repo} does not exist and no template was given")
        shutil.copytree(
            template,
            self.repo,
            ignore=shutil.ignore_patterns("Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs", "*.sln"),
            dirs_exist_ok=True,
        )
        await git(self.repo, "init", "-b", MAIN)
        await git(self.repo, "add", "-A")
        await git(self.repo, "commit", "-m", "Initial ShunyaGame project (from studio template)")
        await git(self.repo, "checkout", "-b", DEVELOP)

    @staticmethod
    def branch_for(task_id: str) -> str:
        return f"agent/{task_id}"

    async def create_worktree(self, task_id: str) -> tuple[str, Path]:
        branch = self.branch_for(task_id)
        path = self.worktrees_dir / task_id
        if (path / ".git").exists():
            return branch, path
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        async with self._repo_lock:
            await git(self.repo, "worktree", "prune")
            exists = (await git(self.repo, "rev-parse", "--verify", "--quiet", branch, check=False)).code == 0
            if exists:
                await git(self.repo, "worktree", "add", str(path), branch)
            else:
                await git(self.repo, "worktree", "add", "-b", branch, str(path), DEVELOP)
        return branch, path

    async def remove_worktree(self, task_id: str) -> None:
        path = self.worktrees_dir / task_id
        async with self._repo_lock:
            if path.exists():
                await git(self.repo, "worktree", "remove", "--force", str(path), check=False)
            await git(self.repo, "worktree", "prune", check=False)

    async def discard_protected_changes(self, worktree: Path) -> list[str]:
        """Revert changes to protected paths (Config/, *.Build.cs, *.uproject, ...).

        Agents cannot write them through tools, but running the Unreal Editor for tests
        rewrites Config/*.ini as a side effect. Nothing under a protected path may ride
        along into an agent's commit, whatever its origin.
        """
        out = (await git(worktree, "status", "--porcelain", "--untracked-files=all")).out
        discarded: list[str] = []
        for line in out.splitlines():
            if len(line) < 4:
                continue
            status, path = line[:2], line[3:].strip().strip('"')
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip('"')
            if not any(fnmatch.fnmatch(path, g) for g in DEFAULT_PROTECTED_GLOBS):
                continue
            if status == "??":
                (worktree / path).unlink(missing_ok=True)
            elif "A" in status:
                await git(worktree, "rm", "-q", "-f", "--cached", "--", path, check=False)
                (worktree / path).unlink(missing_ok=True)
            else:
                await git(worktree, "checkout", "HEAD", "--", path, check=False)
            discarded.append(path)
        return discarded

    async def stage_all(self, worktree: Path) -> None:
        await self.discard_protected_changes(worktree)
        await git(worktree, "add", "-A")

    async def diff(self, worktree: Path, *, stat: bool = False, path: str | None = None) -> str:
        """Diff of the task's own work (committed + uncommitted) since it branched from develop.

        Compared against the merge base, not develop's tip: other tasks merging meanwhile
        must not show up in this task's diff as deletions.
        """
        await self.stage_all(worktree)
        args = ["diff", "--cached", "--no-color", await self.base(worktree)]
        if stat:
            args.insert(3, "--stat")
        if path:
            args += ["--", path]
        return (await git(worktree, *args)).out

    async def changed_files(self, worktree: Path) -> list[str]:
        await self.stage_all(worktree)
        out = (await git(worktree, "diff", "--cached", "--name-only", await self.base(worktree))).out
        return [line.strip() for line in out.splitlines() if line.strip()]

    async def commit_all(self, worktree: Path, message: str, *, author: str) -> str | None:
        await self.stage_all(worktree)
        if (await git(worktree, "diff", "--cached", "--quiet", check=False)).code == 0:
            return await self.head(worktree)
        await git(worktree, "commit", "-m", message, "--author", f"{author} <{author}@agents.shunya.local>")
        return await self.head(worktree)

    async def base(self, worktree: Path) -> str:
        return (await git(worktree, "merge-base", DEVELOP, "HEAD")).out.strip()

    async def head(self, cwd: Path) -> str:
        return (await git(cwd, "rev-parse", "HEAD")).out.strip()

    async def merge_to_develop(self, task_id: str, message: str) -> str:
        branch = self.branch_for(task_id)
        async with self._repo_lock:
            current = (await git(self.repo, "rev-parse", "--abbrev-ref", "HEAD")).out.strip()
            if current != DEVELOP:
                await git(self.repo, "checkout", DEVELOP)
            res = await git(self.repo, "merge", "--no-ff", branch, "-m", message, check=False)
            if res.code != 0:
                await git(self.repo, "merge", "--abort", check=False)
                raise GitError(f"merge of {branch} into develop failed: {res.err or res.out}")
            return await self.head(self.repo)

    async def log(self, ref: str = DEVELOP, n: int = 20) -> list[dict[str, str]]:
        out = (await git(self.repo, "log", ref, f"-{n}", "--pretty=format:%H%x09%an%x09%ad%x09%s", "--date=iso")).out
        rows = []
        for line in out.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                rows.append({"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]})
        return rows


# ------------------------------------------------------------------ agent-facing tools (read-only)


class GitDiff(Tool):
    name = "git_diff"
    description = "Show the diff of this task's changes against the develop branch (stat=true for a summary)."
    required_permissions = ["git_read"]
    activity = AgentState.REVIEWING

    class Input(BaseModel):
        stat: bool = False
        path: str | None = Field(default=None, description="Limit to one file")

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        if args.path:
            sb.resolve(args.path)
        diff = await ctx.services.git.diff(sb.root, stat=args.stat, path=args.path)
        return ToolResult(content=diff or "(no changes against develop)", summary="Inspected diff")


class GitStatus(Tool):
    name = "git_status"
    description = "List files changed in this task's worktree relative to develop."
    required_permissions = ["git_read"]
    activity = AgentState.READING

    class Input(BaseModel):
        pass

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        files = await ctx.services.git.changed_files(sb.root)
        if not files:
            return ToolResult(content="(no changes)", summary="git status: clean")
        return ToolResult(content="\n".join(files), summary=f"git status: {len(files)} changed")


GIT_TOOLS = [GitDiff, GitStatus]

__all__ = ["GIT_TOOLS", "GitError", "GitService", "DEVELOP", "MAIN", "git"]

