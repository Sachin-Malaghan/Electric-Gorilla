"""The OpenAI-compatible provider (routers, gateways, local servers) and choosing it in the studio."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from shunya.api import create_app
from shunya.config import load_settings
from shunya.core.models.base import ChatMessage, ModelProviderError, ToolCallRequest, ToolResultBlock, ToolSpec
from shunya.core.models.openai_compat_provider import OpenAICompatProvider
from shunya.core.models.pricing import CUSTOM_PRICES, cost_usd
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.core.secrets import SecretStore
from shunya.shared.schemas import ModelConfig
from shunya.studio import Studio

from .conftest import FakeBuildService, FakeContentService, FakePackageService, FakePlaytestService, FakeTestService

SECRET = "sk-router-test-0123456789QRST"
URL = "https://router.example/v1"
FAKES = dict(build=FakeBuildService(), tests=FakeTestService(), content=FakeContentService(), playtest=FakePlaytestService(), packager=FakePackageService())
TOOLS = [ToolSpec(name="read_file", description="Read a file", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})]
CONFIG = ModelConfig(model="vendor/some-model", max_tokens=1000)


def _provider(handler, **kw) -> OpenAICompatProvider:
    return OpenAICompatProvider(base_url=URL + "/", api_key=SECRET, transport=httpx.MockTransport(handler), **kw)


def _reply(message: dict, finish: str = "stop", usage: dict | None = None) -> httpx.Response:
    return httpx.Response(200, json={"model": "vendor/some-model", "choices": [{"message": message, "finish_reason": finish}],
                                     "usage": usage or {"prompt_tokens": 120, "completion_tokens": 30}})


async def test_tool_call_round_trip():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL + "/chat/completions" and request.headers["authorization"] == f"Bearer {SECRET}"
        body = json.loads(request.content)
        seen.append(body)
        if len(seen) == 1:
            return _reply({"role": "assistant", "content": None, "extra_field": "kept",
                           "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{\"path\": \"a.txt\"}"}}]},
                          "tool_calls", {"prompt_tokens": 120, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 20}})
        return _reply({"role": "assistant", "content": "done"})

    p = _provider(handler)
    first = await p.generate(system="be brief", messages=[ChatMessage(role="user", text="read a.txt")], tools=TOOLS, config=CONFIG)
    assert first.stop_reason == "tool_use" and first.tool_calls == [ToolCallRequest(id="call_1", name="read_file", arguments={"path": "a.txt"})]
    assert (first.usage.input_tokens, first.usage.cache_read_tokens, first.usage.output_tokens) == (100, 20, 30)
    sent = seen[0]
    assert sent["model"] == "vendor/some-model" and sent["messages"][0] == {"role": "system", "content": "be brief"}
    assert sent["tools"][0]["function"]["name"] == "read_file" and sent["tool_choice"] == "auto"

    history = [ChatMessage(role="user", text="read a.txt"),
               ChatMessage(role="assistant", tool_calls=first.tool_calls, provider_content=first.provider_content),
               ChatMessage(role="user", tool_results=[ToolResultBlock(tool_call_id="call_1", content="hello")])]
    second = await p.generate(system="be brief", messages=history, tools=TOOLS, config=CONFIG)
    assert second.text == "done" and second.stop_reason == "end_turn"
    msgs = seen[1]["messages"]
    assert msgs[2]["extra_field"] == "kept"  # the endpoint's own message goes back untouched
    assert msgs[3] == {"role": "tool", "tool_call_id": "call_1", "content": "hello"}


async def test_bad_arguments_length_and_content_parts():
    replies = iter([
        _reply({"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": "{not json"}}]}),
        _reply({"role": "assistant", "content": [{"type": "text", "text": "par"}, {"type": "text", "text": "tial"}]}, "length"),
    ])
    p = _provider(lambda request: next(replies))
    bad = await p.generate(system="s", messages=[ChatMessage(role="user", text="x")], tools=TOOLS, config=CONFIG)
    assert bad.stop_reason == "tool_use" and "__unparseable_arguments__" in bad.tool_calls[0].arguments and bad.tool_calls[0].id == "call_0"
    cut = await p.generate(system="s", messages=[ChatMessage(role="user", text="x")], tools=[], config=CONFIG)
    assert cut.text == "partial" and cut.stop_reason == "max_tokens"


async def test_a_streamed_reply_is_folded_into_one_message():
    def chunk(delta, finish=None, **extra):
        return "data: " + json.dumps({"model": "routed-model", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extra})

    sse = "\n\n".join([
        chunk({"role": "assistant"}),
        chunk({"content": "Let me "}), chunk({"content": "look."}),
        chunk({"tool_calls": [{"index": 0, "id": "call_9", "type": "function", "function": {"name": "read_file", "arguments": "{\"pa"}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": "th\": \"a.txt\"}"}}]}),
        chunk({}, "tool_calls", usage={"prompt_tokens": 50, "completion_tokens": 9}),
        "data: [DONE]",
    ])

    def handler(request):
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    r = await _provider(handler).generate(system="s", messages=[ChatMessage(role="user", text="x")], tools=TOOLS, config=CONFIG)
    assert r.text == "Let me look." and r.stop_reason == "tool_use" and r.model == "vendor/some-model"
    assert r.tool_calls == [ToolCallRequest(id="call_9", name="read_file", arguments={"path": "a.txt"})]
    assert (r.usage.input_tokens, r.usage.output_tokens) == (50, 9)
    assert r.provider_content[0]["tool_calls"][0]["function"]["arguments"] == '{"path": "a.txt"}'


async def test_errors_never_carry_the_key(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr("shunya.core.models.openai_compat_provider.asyncio.sleep", no_sleep)
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503, text="busy") if calls["n"] < 3 else _reply({"role": "assistant", "content": "ok"})

    assert (await _provider(flaky).generate(system="s", messages=[ChatMessage(role="user", text="x")], tools=[], config=CONFIG)).text == "ok"
    assert calls["n"] == 3  # overloaded endpoints are retried

    for status in (401, 400, 503):
        with pytest.raises(ModelProviderError) as err:
            await _provider(lambda request, status=status: httpx.Response(status, text="nope"), max_retries=1).generate(
                system="s", messages=[ChatMessage(role="user", text="x")], tools=[], config=CONFIG)
        assert SECRET not in str(err.value)

    def refuse(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(ModelProviderError, match="unreachable"):
        await _provider(refuse, max_retries=0).generate(system="s", messages=[ChatMessage(role="user", text="x")], tools=[], config=CONFIG)


def _settings(tmp_path: Path, **overrides):
    return load_settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "ws", engine_root=None, publish_games=False, **overrides)


def test_endpoint_from_the_environment_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("SHUNYA_LLM_BASE_URL", URL)
    monkeypatch.setenv("SHUNYA_LLM_API_KEY", SECRET)
    monkeypatch.setenv("SHUNYA_MODEL_FAST", "vendor/small")
    monkeypatch.setenv("SHUNYA_MODEL_STANDARD", "vendor/medium")
    monkeypatch.setenv("SHUNYA_MODEL_STRONG", "vendor/large")
    monkeypatch.setenv("SHUNYA_MODEL_PRICE_INPUT", "0.5")
    monkeypatch.setenv("SHUNYA_MODEL_PRICE_OUTPUT", "3")
    studio = Studio(_settings(tmp_path), **FAKES)
    try:
        assert isinstance(studio.provider, OpenAICompatProvider) and studio.provider.base_url == URL
        m = studio.model_settings()
        assert m["provider"] == "openai" and m["key_source"] == "environment" and m["base_url"] == URL and m["price_known"]
        assert m["models"] == {"fast": "vendor/small", "standard": "vendor/medium", "strong": "vendor/large"}
        assert SECRET not in json.dumps(m)
        from shunya.core.models.base import Usage

        assert cost_usd("vendor/medium", Usage(input_tokens=1_000_000, output_tokens=1_000_000)) == pytest.approx(3.5)
    finally:
        studio.store.close()
        CUSTOM_PRICES.clear()


def test_choosing_an_endpoint_in_the_office(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(Studio(settings, **FAKES))) as client:
        studio = client.app.state.studio
        assert client.get("/settings/model").json()["any_key_set"] is False
        assert client.post("/settings/model", json={"provider": "openai", "api_key": SECRET}).status_code == 400  # no endpoint
        assert client.post("/settings/model", json={"provider": "openai", "api_key": SECRET, "base_url": URL}).status_code == 400  # no model
        assert client.post("/settings/model", json={"provider": "openai", "base_url": "not a url", "model": "m"}).status_code == 422

        saved = client.post("/settings/model", json={"provider": "openai", "api_key": SECRET, "base_url": URL, "model": "vendor/flash", "max_spend_usd": 4})
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["provider"] == "openai" and body["key_set"] and body["any_key_set"] and body["key_hint"] == "...QRST" and body["base_url"] == URL
        assert set(body["models"].values()) == {"vendor/flash"} and body["price_known"] is False
        assert isinstance(studio.provider, OpenAICompatProvider) and studio.runner.provider is studio.provider
        for path in ("/settings/model", "/studio/state", "/system", "/health"):
            assert SECRET not in client.get(path).text, path
        assert SECRET not in saved.text

    reborn = Studio(_settings(tmp_path), **FAKES)  # endpoint, key and model survive a restart
    try:
        assert isinstance(reborn.provider, OpenAICompatProvider) and reborn.provider.base_url == URL
        assert reborn.settings.model_standard == "vendor/flash"
        reborn.configure_model(provider="scripted", api_key="")
        assert isinstance(reborn.provider, ScriptedProvider) and SecretStore(settings.data_dir).llm_key() == ("", "")
    finally:
        reborn.store.close()
