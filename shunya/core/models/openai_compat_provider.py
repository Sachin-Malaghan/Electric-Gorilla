"""Provider for any OpenAI-compatible chat-completions endpoint (routers, gateways, local servers).

Plain HTTP against `<base_url>/chat/completions` with function calling - no vendor SDK, so
it works with whatever model the endpoint routes to. TLS verification uses the operating
system's trust store, which is what corporate proxies and antivirus HTTPS scanning rely on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import AsyncIterator
from typing import Any

import httpx

from shunya.core.interfaces import IModelProvider
from shunya.core.models.base import ChatMessage, ModelProviderError, ModelResponse, ToolCallRequest, ToolSpec, Usage
from shunya.shared.schemas import ModelConfig

log = logging.getLogger(__name__)
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


def _join_stream(text: str) -> dict[str, Any]:
    """Fold a server-sent-events stream of chat.completion.chunk objects into one chat.completion."""
    message: dict[str, Any] = {"role": "assistant", "content": ""}
    calls: dict[int, dict[str, Any]] = {}
    out: dict[str, Any] = {}
    finish = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:") or line[5:].strip() in ("", "[DONE]"):
            continue
        try:
            chunk = json.loads(line[5:])
        except json.JSONDecodeError:
            continue
        if chunk.get("error"):
            raise ModelProviderError(f"model endpoint error in stream: {str(chunk['error'])[:300]}")
        out["model"] = chunk.get("model") or out.get("model")
        if chunk.get("usage"):
            out["usage"] = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if choice.get("index", 0) != 0:
                continue
            finish = choice.get("finish_reason") or finish
            delta = choice.get("delta") or {}
            for key, value in delta.items():
                if key == "content":
                    message["content"] += value or ""
                elif key == "tool_calls":
                    for n, tc in enumerate(value or []):
                        slot = calls.setdefault(tc.get("index", n), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["function"]["name"] += fn.get("name") or ""
                        slot["function"]["arguments"] += fn.get("arguments") or ""
                        for extra, v in tc.items():  # provider-specific fields the endpoint wants back (e.g. thought signatures)
                            if extra not in ("index", "id", "type", "function") and v is not None:
                                slot[extra] = v
                elif key != "role" and value is not None:
                    message[key] = message[key] + value if isinstance(value, str) and isinstance(message.get(key), str) else value
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
        message["content"] = message["content"] or None
    out["choices"] = [{"index": 0, "message": message, "finish_reason": finish}]
    return out


class OpenAICompatProvider(IModelProvider):
    name = "openai"

    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 600.0, max_retries: int = 3, transport: httpx.AsyncBaseTransport | None = None):
        if not base_url:
            raise ValueError("an endpoint URL is required for the OpenAI-compatible provider")
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout_s
        self._max_retries = max_retries
        self._transport = transport
        self._ssl = ssl.create_default_context()

    # ------------------------------------------------------------------ conversion

    @staticmethod
    def _to_api_messages(system: str, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "assistant":
                if m.provider_content:  # the endpoint's own message, replayed verbatim (keeps any provider-specific fields)
                    out.append(m.provider_content[0])
                    continue
                msg: dict[str, Any] = {"role": "assistant", "content": m.text or None}
                if m.tool_calls:
                    msg["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}} for tc in m.tool_calls]
                out.append(msg)
            else:
                for r in m.tool_results:
                    out.append({"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content})
                if m.text:
                    out.append({"role": "user", "content": m.text})
        return out

    @staticmethod
    def _tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools]

    @staticmethod
    def _parse(data: dict[str, Any], requested_model: str) -> ModelResponse:
        choices = data.get("choices") or []
        if not choices:
            raise ModelProviderError(f"the endpoint returned no choices: {str(data)[:300]}")
        choice = choices[0]
        message = choice.get("message") or {}
        calls: list[ToolCallRequest] = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function") or {}
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(args, dict):
                    raise ValueError("arguments are not an object")
            except (json.JSONDecodeError, ValueError):
                # let the tool's own validation reject it with a readable message the model can act on
                args = {"__unparseable_arguments__": str(raw)[:500]}
            calls.append(ToolCallRequest(id=tc.get("id") or f"call_{i}", name=fn.get("name") or "", arguments=args))
        content = message.get("content")
        if isinstance(content, list):  # some gateways return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        finish = choice.get("finish_reason") or ("tool_calls" if calls else "stop")
        stop = {"tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens", "content_filter": "refusal"}.get(finish, "end_turn")
        if calls and stop == "end_turn":
            stop = "tool_use"
        usage = data.get("usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return ModelResponse(
            text=content or "", tool_calls=calls, stop_reason=stop, stop_detail="content_filter" if stop == "refusal" else None,
            usage=Usage(input_tokens=max(0, (usage.get("prompt_tokens") or 0) - cached), output_tokens=usage.get("completion_tokens") or 0, cache_read_tokens=cached),
            # the id we asked for, not the router's internal name for it: pricing and the cost ledger key on it
            model=requested_model or data.get("model") or "", provider_content=[message] if message else None,
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        last = ""
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout, verify=self._ssl, transport=self._transport) as client:
                    r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            except httpx.HTTPError as e:
                last = f"endpoint unreachable: {type(e).__name__}: {e}"
            else:
                if r.status_code == 200:
                    if r.text.lstrip().startswith("data:"):  # some routers stream even when asked not to
                        return _join_stream(r.text)
                    try:
                        return r.json()
                    except ValueError:
                        raise ModelProviderError(f"the endpoint did not return JSON: {r.text[:200]}") from None
                detail = r.text[:400]
                if r.status_code in (401, 403):
                    raise ModelProviderError(f"the endpoint rejected the API key ({r.status_code}): {detail}")
                if r.status_code not in RETRYABLE:
                    raise ModelProviderError(f"model endpoint error {r.status_code}: {detail}")
                last = f"model endpoint error {r.status_code}: {detail}"
            if attempt < self._max_retries:
                await asyncio.sleep(min(2.0 * (2**attempt), 20.0))
        raise ModelProviderError(f"{last} (after {self._max_retries + 1} attempts)")

    # ------------------------------------------------------------------ interface

    async def generate(self, *, system, messages, tools, config: ModelConfig, agent_id="") -> ModelResponse:
        payload: dict[str, Any] = {"model": config.model, "messages": self._to_api_messages(system, messages), "max_tokens": config.max_tokens, "stream": False}
        if tools:
            payload["tools"] = self._tools(tools)
            payload["tool_choice"] = "auto"
        return self._parse(await self._post(payload), config.model or "")

    async def structured_generate(self, *, system, messages, schema, config: ModelConfig, agent_id=""):
        payload = {
            "model": config.model, "max_tokens": config.max_tokens, "response_format": {"type": "json_object"}, "stream": False,
            "messages": self._to_api_messages(system + "\n\nReply with one JSON object matching this JSON schema, and nothing else:\n" + json.dumps(schema), messages),
        }
        resp = self._parse(await self._post(payload), config.model or "")
        try:
            return json.loads(resp.text), resp
        except json.JSONDecodeError as e:
            raise ModelProviderError("structured output was not valid JSON") from e

    async def stream(self, *, system, messages, config: ModelConfig, agent_id="") -> AsyncIterator[str]:  # type: ignore[override]
        resp = await self.generate(system=system, messages=messages, tools=[], config=config, agent_id=agent_id)
        yield resp.text

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=30, verify=self._ssl, transport=self._transport) as client:
            r = await client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self._key}"})
        if r.status_code != 200:
            raise ModelProviderError(f"could not list models ({r.status_code}): {r.text[:200]}")
        return [m.get("id", "") for m in (r.json().get("data") or [])]
