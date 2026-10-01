"""Safe filesystem tools (spec 16 - Files). All paths go through the workspace sandbox."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from shunya.shared.schemas import AgentState
from shunya.tools.base import Tool, ToolContext, ToolError, ToolResult

SKIP_DIRS = {".git", "Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs", "__pycache__", "node_modules"}
TEXT_EXT = {".h", ".hpp", ".cpp", ".c", ".inl", ".cs", ".ini", ".uproject", ".uplugin", ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".usf", ".ush", ".hlsl", ".csv"}


def _is_text(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in TEXT_EXT


class ReadFile(Tool):
    name = "read_file"
    description = "Read a text file in the workspace. Returns numbered lines. Use start_line/end_line for large files."
    required_permissions = ["read_code"]
    activity = AgentState.READING

    class Input(BaseModel):
        path: str = Field(description="Workspace-relative path, e.g. Source/ShunyaGame/ShunyaGame.Build.cs")
        start_line: int = Field(default=1, ge=1)
        end_line: int | None = Field(default=None, ge=1)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        path = sb.resolve(args.path)
        if not path.is_file():
            raise ToolError(f"no such file: {args.path}")
        if path.stat().st_size > sb.max_file_bytes:
            raise ToolError(f"{args.path} is too large to read whole; use search_files")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        end = min(args.end_line or len(lines), len(lines))
        body = "\n".join(f"{i:5d}| {lines[i - 1]}" for i in range(args.start_line, end + 1))
        rel = sb.relative(path)
        return ToolResult(content=body or "(empty file)", summary=f"Read {rel}", files_read=[rel], data={"lines": len(lines)})


class ListDir(Tool):
    name = "list_dir"
    description = "List files and folders under a workspace directory (build output folders are skipped)."
    required_permissions = ["read_code"]
    activity = AgentState.READING

    class Input(BaseModel):
        path: str = Field(default=".", description="Workspace-relative directory")
        depth: int = Field(default=2, ge=1, le=6)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        root = sb.resolve(args.path)
        if not root.is_dir():
            raise ToolError(f"no such directory: {args.path}")
        out: list[str] = []
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            depth = len(os.path.normpath(dirpath).split(os.sep)) - base_depth
            if depth >= args.depth:
                dirnames[:] = []
            rel_dir = sb.relative(Path(dirpath))
            for f in sorted(filenames):
                out.append(f"{rel_dir}/{f}" if rel_dir != "." else f)
            if len(out) > 400:
                out.append("... (truncated)")
                break
        return ToolResult(content="\n".join(out) or "(empty)", summary=f"Listed {args.path}")


class SearchFiles(Tool):
    name = "search_files"
    description = "Regex search across text files in the workspace. Returns path:line: text matches."
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        pattern: str = Field(description="Python regular expression")
        path: str = Field(default=".", description="Directory to search under")
        glob: str = Field(default="*", description="Filename glob, e.g. *.h")
        max_results: int = Field(default=80, ge=1, le=400)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        root = sb.resolve(args.path)
        try:
            rx = re.compile(args.pattern)
        except re.error as e:
            raise ToolError(f"bad regex: {e}") from None
        hits: list[str] = []
        files = [root] if root.is_file() else []
        if root.is_dir():
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for f in filenames:
                    if _is_text(f) and fnmatch.fnmatch(f, args.glob):
                        files.append(Path(dirpath) / f)
        for f in sorted(files):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{sb.relative(f)}:{i}: {line.strip()[:200]}")
                    if len(hits) >= args.max_results:
                        break
            if len(hits) >= args.max_results:
                break
        return ToolResult(content="\n".join(hits) or "(no matches)", summary=f"Searched /{args.pattern}/ in {args.path} ({len(hits)} hits)")


class CreateFile(Tool):
    name = "create_file"
    description = "Create a new file (or overwrite one when overwrite=true) inside your writable areas of the task worktree."
    required_permissions = ["write_code"]
    activity = AgentState.CODING

    class Input(BaseModel):
        path: str
        content: str
        overwrite: bool = False

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        path = sb.resolve(args.path, for_write=True)
        if path.exists() and not args.overwrite:
            raise ToolError(f"{args.path} already exists; use patch_file or overwrite=true")
        if len(args.content.encode("utf-8")) > sb.max_file_bytes:
            raise ToolError("file content too large")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8", newline="\n")
        rel = sb.relative(path)
        return ToolResult(content=f"Wrote {rel} ({len(args.content.splitlines())} lines)", summary=f"Created {rel}", files_written=[rel])


class PatchFile(Tool):
    name = "patch_file"
    description = (
        "Edit a file by exact string replacement. old_text must match exactly once "
        "(or set replace_all=true). Include enough surrounding context to be unique."
    )
    required_permissions = ["write_code"]
    activity = AgentState.CODING

    class Input(BaseModel):
        path: str
        old_text: str = Field(min_length=1)
        new_text: str
        replace_all: bool = False

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        path = sb.resolve(args.path, for_write=True)
        if not path.is_file():
            raise ToolError(f"no such file: {args.path}")
        text = path.read_text(encoding="utf-8")
        count = text.count(args.old_text)
        if count == 0:
            raise ToolError("old_text not found; read the file again and copy the exact text")
        if count > 1 and not args.replace_all:
            raise ToolError(f"old_text matches {count} times; add context or set replace_all=true")
        text = text.replace(args.old_text, args.new_text) if args.replace_all else text.replace(args.old_text, args.new_text, 1)
        path.write_text(text, encoding="utf-8", newline="\n")
        rel = sb.relative(path)
        return ToolResult(content=f"Patched {rel} ({count if args.replace_all else 1} replacement)", summary=f"Modified {rel}", files_written=[rel])


FILE_TOOLS = [ReadFile, ListDir, SearchFiles, CreateFile, PatchFile]
