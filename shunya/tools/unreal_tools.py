"""Live Unreal Editor tools through the bridge (spec 16 - Unreal, 18).

Read, editor-modify and runtime tools carry different required permissions.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from shunya.bridge import BridgeUnavailable
from shunya.shared.schemas import AgentState
from shunya.tools.base import Tool, ToolContext, ToolError, ToolResult


class _Empty(BaseModel):
    pass


class _BridgeQuery(Tool):
    route: ClassVar[str]
    required_permissions = ["unreal_read"]
    activity = AgentState.READING
    Input = _Empty

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        try:
            data = await ctx.services.bridge.query(self.route, args.model_dump(exclude_none=True))
        except BridgeUnavailable as e:
            raise ToolError(str(e)) from None
        return ToolResult(content=json.dumps(data, indent=1)[:20000], summary=f"Unreal {self.route}", data=data)


class _BridgeCommand(Tool):
    command: ClassVar[str]
    scope: ClassVar[str] = "editor"
    required_permissions = ["unreal_editor_modify"]
    activity = AgentState.CODING
    Input = _Empty

    async def run(self, ctx: ToolContext, args: BaseModel) -> ToolResult:
        try:
            data = await ctx.services.bridge.command(self.command, args.model_dump(exclude_none=True), self.scope)
        except BridgeUnavailable as e:
            raise ToolError(str(e)) from None
        return ToolResult(ok=bool(data.get("ok", True)), content=json.dumps(data, indent=1)[:8000], summary=f"Unreal {self.command}", data=data)


class GetEditorState(_BridgeQuery):
    name = "get_editor_state"
    description = "Unreal Editor status: engine version, project, open level, whether Play-In-Editor is running."
    route = "status"


class GetCurrentLevel(_BridgeQuery):
    name = "get_current_level"
    description = "The level open in the editor: name, path and actor counts by class."
    route = "level"


class FindActor(_BridgeQuery):
    name = "find_actor"
    description = "Find actors in the open level by name substring and/or class name."
    route = "actors"

    class Input(BaseModel):
        name: str | None = None
        class_name: str | None = Field(default=None, description="e.g. StaticMeshActor")
        limit: int = Field(default=50, ge=1, le=500)


class InspectActor(_BridgeQuery):
    name = "inspect_actor"
    description = "Transform, class, components and editable properties of one actor (by exact name or label)."
    route = "actor"

    class Input(BaseModel):
        name: str


class InspectAsset(_BridgeQuery):
    name = "inspect_asset"
    description = "Asset registry metadata for assets under a content path, e.g. /Game/Characters. Blueprints report their parent class."
    route = "assets"

    class Input(BaseModel):
        path: str = "/Game"
        class_name: str | None = None
        limit: int = Field(default=100, ge=1, le=1000)


class SpawnActor(_BridgeCommand):
    name = "spawn_actor"
    description = "Spawn an actor of a class in the open editor level at a location (undoable editor transaction)."
    command = "spawn_actor"

    class Input(BaseModel):
        class_path: str = Field(description="e.g. /Script/Engine.PointLight or /Script/ShunyaGame.MyActor")
        x: float = 0.0
        y: float = 0.0
        z: float = 0.0
        label: str | None = None


class SetProperty(_BridgeCommand):
    name = "set_property"
    description = "Set an editable property on an actor (or one of its components: Component.Property) from text."
    command = "set_property"

    class Input(BaseModel):
        actor: str
        property: str
        value: str


class LoadLevel(_BridgeCommand):
    name = "load_level"
    description = "Open a level in the editor by package path, e.g. /Game/Maps/L_Test."
    command = "load_level"

    class Input(BaseModel):
        path: str


class SaveLevel(_BridgeCommand):
    name = "save_level"
    description = "Save the level currently open in the editor."
    command = "save_level"


class StartPie(_BridgeCommand):
    name = "start_pie"
    description = "Start a Play-In-Editor session."
    command = "start_pie"
    activity = AgentState.TESTING


class StopPie(_BridgeCommand):
    name = "stop_pie"
    description = "Stop the Play-In-Editor session."
    command = "stop_pie"
    activity = AgentState.TESTING


class CaptureScreenshot(_BridgeCommand):
    name = "capture_screenshot"
    description = "Capture the active editor/PIE viewport to a PNG under the project's Saved/Screenshots; returns the path."
    command = "capture_screenshot"
    activity = AgentState.TESTING


class GetRuntimeTelemetry(_BridgeQuery):
    name = "get_runtime_telemetry"
    description = "Runtime telemetry from the running PIE world: FPS, frame time, player pawn position, actor count."
    route = "telemetry"
    required_permissions = ["unreal_runtime"]
    activity = AgentState.TESTING


UNREAL_TOOLS: list[type[Any]] = [
    GetEditorState, GetCurrentLevel, FindActor, InspectActor, InspectAsset,
    SpawnActor, SetProperty, LoadLevel, SaveLevel, StartPie, StopPie, CaptureScreenshot, GetRuntimeTelemetry,
]
