"""Request/response mapping of the Claude provider, against a stub client (no network, no cost)."""

from __future__ import annotations

from types import SimpleNamespace

from shunya.core.models.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from shunya.core.models.base import ChatMessage, ToolCallRequest, ToolResultBlock, ToolSpec
from shunya.shared.schemas import ModelConfig


class _Block(SimpleNamespace):
    def model_dump(self, **_):
        return dict(self.__dict__)


class _Stream:
    def __init__(self, message):
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self._message


class _StubClient:
    def __init__(self, message):
        self.calls: list[dict] = []
        outer = self

        class _Messages:
            def stream(self, **kwargs):
                outer.calls.append(kwargs)
                return _Stream(message)

        self.beta = SimpleNamespace(messages=_Messages())


def _message(stop_reason="tool_use"):
    return SimpleNamespace(
        content=[
            _Block(type="thinking", thinking="", signature="sig"),
            _Block(type="text", text="Reading the build file."),
            _Block(type="tool_use", id="toolu_1", name="read_file", input={"path": "Source/A.Build.cs"}),
        ],
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=900, cache_creation_input_tokens=0),
    )


TOOLS = [ToolSpec(name="read_file", description="Read a file", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})]
CONFIG = ModelConfig(model="claude-opus-5-5", effort="medium", max_tokens=32000)


async def test_request_shape_and_response_parsing():
    client = _StubClient(_message())
    provider = AnthropicProvider(client=client)
    resp = await provider.generate(system="You are Arjun.", messages=[ChatMessage(role="user", text="Do the task.")], tools=TOOLS, config=CONFIG)

    req = client.calls[0]
    assert req["model"] == "claude-opus-5-5" and req["max_tokens"] == 32000
    assert req["thinking"] == {"type": "adaptive"} and req["output_config"] == {"effort": "medium"}
    assert "temperature" not in req and "tool_choice" not in req  # rejected by current models
    assert req["betas"] == [FALLBACK_BETA] and req["fallbacks"] == "default"
    assert req["system"] == [{"type": "text", "text": "You are Arjun."}] and req["cache_control"] == {"type": "ephemeral"}
    assert req["tools"][0]["name"] == "read_file" and req["tools"][0]["eager_input_streaming"] is True
    assert req["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Do the task."}]}]

    assert resp.stop_reason == "tool_use" and resp.text == "Reading the build file."
    assert resp.tool_calls == [ToolCallRequest(id="toolu_1", name="read_file", arguments={"path": "Source/A.Build.cs"})]
    assert (resp.usage.input_tokens, resp.usage.output_tokens, resp.usage.cache_read_tokens) == (1200, 80, 900)
    assert [b["type"] for b in resp.provider_content] == ["thinking", "text", "tool_use"]


async def test_history_is_replayed_verbatim_with_tool_results_in_one_user_turn():
    client = _StubClient(_message())
    provider = AnthropicProvider(client=client, use_fallbacks=False)
    first = await provider.generate(system="s", messages=[ChatMessage(role="user", text="go")], tools=TOOLS, config=CONFIG)
    history = [
        ChatMessage(role="user", text="go"),
        first.as_assistant_message(),
        ChatMessage(role="user", tool_results=[ToolResultBlock(tool_call_id="toolu_1", content="file body", is_error=False)]),
    ]
    await provider.generate(system="s", messages=history, tools=TOOLS, config=CONFIG)
    req = client.calls[1]
    assert "betas" not in req and "fallbacks" not in req
    assistant, results = req["messages"][1], req["messages"][2]
    # thinking blocks go back unchanged: history is append-only
    assert assistant["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert results == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "file body", "is_error": False}]}


async def test_refusal_is_surfaced():
    provider = AnthropicProvider(client=_StubClient(_message("refusal")))
    resp = await provider.generate(system="s", messages=[ChatMessage(role="user", text="go")], tools=[], config=CONFIG)
    assert resp.stop_reason == "refusal" and resp.stop_detail == "cyber"
