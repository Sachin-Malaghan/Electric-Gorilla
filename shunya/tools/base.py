"""Tool architecture (spec 16): typed inputs, required permissions, registry-mediated execution.

Execution path for every tool call (spec 30):
  authority/permission check -> input schema validation -> argument/path validation
  (inside the tool, via the sandbox) -> execution -> bounded, structured result.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ValidationError

from shunya.core.interfaces import ITool
from shunya.core.models.base import ToolSpec
from shunya.core.permissions import PermissionDenied, PermissionEngine, WorkspaceSandbox
from shunya.shared.schemas import AgentProfile, AgentRun, AgentState, Task

if TYPE_CHECKING:
    from shunya.tools.services import ToolServices

MAX_RESULT_CHARS = 24_000


class ToolResult(BaseModel):
    ok: bool = True
    content: str = ""  # what the model sees
    summary: str = ""  # one line for the operational trace
    data: dict[str, Any] = {}
    files_read: list[str] = []
    files_written: list[str] = []
    terminal: bool = False  # e.g. submit_report: ends the run


class ToolError(Exception):
    """An expected failure the agent should see and recover from (bad path, no match, ...)."""


@dataclass
class ToolContext:
    agent: AgentProfile
    run: AgentRun
    services: ToolServices
    task: Task | None = None
    sandbox: WorkspaceSandbox | None = None
    set_activity: Callable[[AgentState, str], Awaitable[None]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    async def activity(self, state: AgentState, action: str) -> None:
        if self.set_activity:
            await self.set_activity(state, action)

    def require_sandbox(self) -> WorkspaceSandbox:
        if self.sandbox is None:
            raise ToolError("this tool needs a task workspace, and none is attached to this run")
        return self.sandbox


class Tool(ITool):
    name: ClassVar[str]
    description: ClassVar[str]
    required_permissions: ClassVar[list[str]] = []
    activity: ClassVar[AgentState] = AgentState.READING
    Input: ClassVar[type[BaseModel]]

    @property
    def input_schema(self) -> dict[str, Any]:
        schema = self.Input.model_json_schema()
        schema.pop("title", None)
        return schema

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema=self.input_schema)

    def describe_call(self, args: BaseModel) -> str:
        first = next(iter(args.model_dump().values()), "")
        return f"{self.name} {str(first)[:80]}".strip()

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        args = self.Input.model_validate(arguments)
        return await self.run(context, args)

    async def run(self, ctx: ToolContext, args: Any) -> ToolResult:  # pragma: no cover - abstract
        raise NotImplementedError


class ToolRegistry:
    def __init__(self, permissions: PermissionEngine):
        self._tools: dict[str, Tool] = {}
        self.permissions = permissions

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs_for(self, profile: AgentProfile, *, extra: list[Tool] | None = None) -> list[ToolSpec]:
        tools = [self._tools[n] for n in profile.tools if n in self._tools]
        tools += extra or []
        return [t.spec() for t in tools]

    async def execute(self, ctx: ToolContext, name: str, arguments: dict[str, Any], *, extra: dict[str, Tool] | None = None) -> tuple[ToolResult, int]:
        """Returns (result, latency_ms). Never raises for agent-caused errors."""
        started = time.perf_counter()
        tool = (extra or {}).get(name) or self._tools.get(name)
        try:
            if tool is None:
                raise ToolError(f"unknown tool '{name}'")
            if name not in (extra or {}):
                isolated = bool(ctx.sandbox and ctx.sandbox.isolated)
                self.permissions.require(ctx.agent, name, tool.required_permissions, isolated_workspace=isolated)
            try:
                args = tool.Input.model_validate(arguments if isinstance(arguments, dict) else {})
            except ValidationError as e:
                raise ToolError(f"invalid arguments for {name}: {e.errors(include_url=False)}") from None
            await ctx.activity(tool.activity, tool.describe_call(args))
            result = await tool.run(ctx, args)
        except PermissionDenied as e:
            result = ToolResult(ok=False, content=f"PERMISSION DENIED: {e}", summary=f"{name} denied: {e}")
        except ToolError as e:
            result = ToolResult(ok=False, content=f"ERROR: {e}", summary=f"{name} failed: {e}")
        except Exception as e:  # noqa: BLE001 - tool bugs must not kill the run; they are reported
            result = ToolResult(ok=False, content=f"INTERNAL TOOL ERROR: {type(e).__name__}: {e}", summary=f"{name} crashed: {e}")
        if len(result.content) > MAX_RESULT_CHARS:
            result.content = result.content[:MAX_RESULT_CHARS] + f"\n... [truncated {len(result.content) - MAX_RESULT_CHARS} chars]"
        return result, int((time.perf_counter() - started) * 1000)
