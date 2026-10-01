"""Vendor-neutral model types (spec 15). Agents depend on these, never on a vendor SDK."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    tool_results: list[ToolResultBlock] = Field(default_factory=list)
    # Assistant turns keep the provider's native content blocks (e.g. thinking blocks)
    # so they can be replayed verbatim - conversation history is append-only.
    provider_content: list[dict[str, Any]] | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


class ModelResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    stop_reason: str = "end_turn"  # end_turn | tool_use | max_tokens | refusal | error
    stop_detail: str | None = None
    usage: Usage = Field(default_factory=Usage)
    model: str = ""
    provider_content: list[dict[str, Any]] | None = None

    def as_assistant_message(self) -> ChatMessage:
        return ChatMessage(role="assistant", text=self.text, tool_calls=self.tool_calls, provider_content=self.provider_content)


class ModelProviderError(Exception):
    """Raised for provider failures the runtime should treat as a recoverable tool-less failure."""
