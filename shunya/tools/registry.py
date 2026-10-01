"""Default tool registry (spec 16). Note there is deliberately no shell tool."""

from __future__ import annotations

from shunya.core.permissions import PermissionEngine
from shunya.tools.base import ToolRegistry
from shunya.tools.code_tools import CODE_TOOLS
from shunya.tools.content_tools import CONTENT_TOOLS
from shunya.tools.filesystem import DOC_TOOLS, FILE_TOOLS
from shunya.tools.git_tools import GIT_TOOLS
from shunya.tools.unreal_tools import UNREAL_TOOLS


def build_registry(permissions: PermissionEngine | None = None) -> ToolRegistry:
    registry = ToolRegistry(permissions or PermissionEngine())
    for cls in [*FILE_TOOLS, *DOC_TOOLS, *GIT_TOOLS, *CODE_TOOLS, *CONTENT_TOOLS, *UNREAL_TOOLS]:
        registry.register(cls())
    return registry
