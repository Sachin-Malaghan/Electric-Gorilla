"""Claude provider (Anthropic SDK). The only module in the studio that imports a vendor SDK."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from shunya.core.interfaces import IModelProvider
from shunya.core.models.base import ChatMessage, ModelProviderError, ModelResponse, ToolCallRequest, ToolSpec, Usage
from shunya.shared.schemas import ModelConfig

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a JSON schema acceptable to structured outputs: closed objects, all keys required."""

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


class AnthropicProvider(IModelProvider):
    name = "anthropic"

    def __init__(self, *, use_fallbacks: bool = True, client: Any | None = None):
        if client is None:
            import anthropic

            client = anthropic.AsyncAnthropic()
        self._client = client
        self._use_fallbacks = use_fallbacks

    # ------------------------------------------------------------------ conversion

    @staticmethod
    def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "assistant":
                if m.provider_content is not None:
                    content = m.provider_content
                else:
                    content = []
                    if m.text:
                        content.append({"type": "text", "text": m.text})
                    for tc in m.tool_calls:
                        content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                out.append({"role": "assistant", "content": content})
            else:
                content = [
                    {"type": "tool_result", "tool_use_id": r.tool_call_id, "content": r.content, "is_error": r.is_error}
                    for r in m.tool_results
                ]
                if m.text:
                    content.append({"type": "text", "text": m.text})
                out.append({"role": "user", "content": content})
        return out

    @staticmethod
    def _tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        # eager_input_streaming: large inputs (whole source files) stream as generated.
        # The tool registry validates every parsed input against its schema before running it.
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema, "eager_input_streaming": True}
            for t in tools
        ]

    def _common(self, system: str, config: ModelConfig) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            # Stable role prompt first; automatic caching covers the growing history.
            "system": [{"type": "text", "text": system}],
            "cache_control": {"type": "ephemeral"},
            "thinking": {"type": "adaptive"},
        }
        output_config: dict[str, Any] = {}
        if config.effort:
            output_config["effort"] = config.effort
        if output_config:
            kwargs["output_config"] = output_config
        if self._use_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    @staticmethod
    def _parse(msg: Any) -> ModelResponse:
        text_parts: list[str] = []
        calls: list[ToolCallRequest] = []
        for block in msg.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = block.input if isinstance(block.input, dict) else {}
                calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=args))
        u = msg.usage
        usage = Usage(
            input_tokens=getattr(u, "input_tokens", 0) or 0,
            output_tokens=getattr(u, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        detail = None
        if msg.stop_reason == "refusal" and getattr(msg, "stop_details", None) is not None:
            detail = getattr(msg.stop_details, "category", None)
        return ModelResponse(
            text="\n".join(text_parts),
            tool_calls=calls,
            stop_reason=msg.stop_reason or "end_turn",
            stop_detail=detail,
            usage=usage,
            model=getattr(msg, "model", "") or "",
            provider_content=[b.model_dump(mode="json", exclude_none=True) for b in msg.content],
        )

    async def _final_message(self, **kwargs: Any) -> Any:
        import anthropic

        try:
            async with self._client.beta.messages.stream(**kwargs) as stream:
                return await stream.get_final_message()
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError, anthropic.BadRequestError) as e:
            raise ModelProviderError(f"non-retryable model error {e.status_code}: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise ModelProviderError(f"rate limited after SDK retries: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise ModelProviderError(f"model API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ModelProviderError(f"model API unreachable: {e}") from e

    # ------------------------------------------------------------------ interface

    async def generate(self, *, system, messages, tools, config, agent_id="") -> ModelResponse:
        kwargs = self._common(system, config)
        kwargs["messages"] = self._to_api_messages(messages)
        if tools:
            kwargs["tools"] = self._tools(tools)
        msg = await self._final_message(**kwargs)
        return self._parse(msg)

    async def structured_generate(self, *, system, messages, schema, config, agent_id=""):
        kwargs = self._common(system, config)
        kwargs["messages"] = self._to_api_messages(messages)
        kwargs.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": strict_schema(schema)}
        msg = await self._final_message(**kwargs)
        resp = self._parse(msg)
        if resp.stop_reason == "refusal":
            raise ModelProviderError(f"model declined the request ({resp.stop_detail})")
        try:
            return json.loads(resp.text), resp
        except json.JSONDecodeError as e:
            raise ModelProviderError(f"structured output was not valid JSON (stop_reason={resp.stop_reason})") from e

    async def stream(self, *, system, messages, config, agent_id="") -> AsyncIterator[str]:  # type: ignore[override]
        kwargs = self._common(system, config)
        kwargs["messages"] = self._to_api_messages(messages)
        async with self._client.beta.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
