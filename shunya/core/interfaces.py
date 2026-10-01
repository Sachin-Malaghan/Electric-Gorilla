"""Stable interfaces (spec 50).

Concrete implementations live next to the subsystem that owns them; the rest of the
studio depends only on these contracts, so e.g. InMemoryEventBus and RedisEventBus are
interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shunya.shared.schemas import (
    AgentProfile,
    AgentRun,
    Approval,
    Artifact,
    ArtifactType,
    Event,
    MemoryKind,
    MemoryRecord,
    Task,
    TaskStatus,
)

if TYPE_CHECKING:
    from shunya.core.models.base import ChatMessage, ModelResponse, ToolSpec
    from shunya.shared.schemas import ModelConfig


class IEventBus(ABC):
    @abstractmethod
    async def publish(self, event: Event) -> Event: ...

    @abstractmethod
    def subscribe(self) -> AsyncIterator[Event]: ...


class IModelProvider(ABC):
    name: str

    @abstractmethod
    async def generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        config: ModelConfig,
        agent_id: str = "",
    ) -> ModelResponse: ...

    @abstractmethod
    async def structured_generate(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        config: ModelConfig,
        agent_id: str = "",
    ) -> tuple[dict[str, Any], ModelResponse]: ...

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        config: ModelConfig,
        agent_id: str = "",
    ) -> AsyncIterator[str]: ...


class ITool(ABC):
    name: str
    description: str
    required_permissions: list[str]

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, context: Any, arguments: dict[str, Any]) -> Any: ...


class IAgent(ABC):
    profile: AgentProfile

    @abstractmethod
    async def run(self, task: Task, instructions: str, **kwargs: Any) -> AgentRun: ...


class ITaskRepository(ABC):
    @abstractmethod
    def get(self, task_id: str) -> Task | None: ...

    @abstractmethod
    def save(self, task: Task) -> Task: ...

    @abstractmethod
    def list(self, *, status: TaskStatus | None = None, parent_id: str | None = None) -> list[Task]: ...

    @abstractmethod
    def next_id(self, prefix: str) -> str: ...


class IMemoryProvider(ABC):
    @abstractmethod
    def remember(self, record: MemoryRecord) -> MemoryRecord: ...

    @abstractmethod
    def recall(self, query: str, *, kind: MemoryKind | None = None, agent_id: str | None = None, limit: int = 5) -> list[MemoryRecord]: ...


class IKnowledgeRetriever(ABC):
    @abstractmethod
    def search(self, query: str, *, limit: int = 8, max_chars: int = 12000) -> list[dict[str, Any]]: ...


class IUnrealBridge(ABC):
    @abstractmethod
    async def status(self) -> dict[str, Any]: ...

    @abstractmethod
    async def query(self, route: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def command(self, command: str, args: dict[str, Any], scope: str) -> dict[str, Any]: ...


class ISandbox(ABC):
    """An isolated working copy an agent may modify."""

    root: Path

    @abstractmethod
    def resolve(self, relative_path: str, *, for_write: bool = False) -> Path: ...


class IArtifactStore(ABC):
    @abstractmethod
    def put(self, *, type: ArtifactType, title: str, creator: str, content: str | bytes, task_id: str | None = None, content_type: str = "text/plain", metadata: dict[str, Any] | None = None) -> Artifact: ...

    @abstractmethod
    def read(self, artifact_id: str) -> bytes: ...

    @abstractmethod
    def get(self, artifact_id: str) -> Artifact | None: ...


class IApprovalService(ABC):
    @abstractmethod
    async def request(self, approval: Approval) -> Approval: ...

    @abstractmethod
    async def decide(self, approval_id: str, *, granted: bool, decided_by: str, comment: str = "") -> Approval: ...

    @abstractmethod
    async def wait(self, approval_id: str) -> Approval: ...
