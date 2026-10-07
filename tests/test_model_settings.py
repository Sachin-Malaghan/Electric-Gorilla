"""Supplying the API key, switching to real agents, and the studio-wide spending cap."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import BaseModel

from shunya.api import create_app
from shunya.config import load_settings
from shunya.core.agent_runtime import RunControl, RunRequest
from shunya.core.interfaces import IModelProvider
from shunya.core.models.anthropic_provider import AnthropicProvider
from shunya.core.models.base import ModelResponse, ToolCallRequest, Usage
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.core.permissions import WorkspaceSandbox
from shunya.core.secrets import SecretStore, hint
from shunya.shared.schemas import RunStatus
from shunya.studio import Studio

from .conftest import FakeBuildService, FakeContentService, FakePackageService, FakePlaytestService, FakeTestService

SECRET = "sk-ant-test-0123456789abcdefWXYZ"
FAKES = dict(build=FakeBuildService(), tests=FakeTestService(), content=FakeContentService(), playtest=FakePlaytestService(), packager=FakePackageService())


def _settings(tmp_path: Path, **overrides):
    return load_settings(data_dir=tmp_path / "data", workspace_dir=tmp_path / "ws", game_repo=tmp_path / "ws" / "ShunyaGame", engine_root=None, **overrides)


def test_secret_store_round_trip_and_hint(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store = SecretStore(tmp_path)
    assert store.anthropic_key() == ("", "")
    store.set("anthropic_api_key", SECRET)
    assert SecretStore(tmp_path).anthropic_key() == (SECRET, "office settings")
    assert hint(SECRET) == "...WXYZ" and SECRET not in hint(SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key-000000000000")
    assert store.anthropic_key() == ("sk-ant-env-key-000000000000", "environment")  # the operator's environment wins
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    store.set("anthropic_api_key", "")
    assert store.anthropic_key() == ("", "")


def test_a_supplied_key_switches_the_studio_to_real_agents(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SHUNYA_MODEL_PROVIDER", raising=False)
    settings = _settings(tmp_path)
    assert not settings.provider_pinned
    studio = Studio(settings, **FAKES)
    assert isinstance(studio.provider, ScriptedProvider)  # no key anywhere: scripted
    studio.store.close()

    SecretStore(settings.data_dir).set("anthropic_api_key", SECRET)
    reborn = Studio(_settings(tmp_path), **FAKES)  # after a restart the stored key is picked up
    assert isinstance(reborn.provider, AnthropicProvider) and reborn.settings.model_provider == "anthropic"
    assert reborn.runner.provider is reborn.provider
    assert reborn.provider._client.api_key == SECRET
    reborn.store.close()

    monkeypatch.setenv("SHUNYA_MODEL_PROVIDER", "scripted")  # an explicit choice is respected even with a key present
    pinned = Studio(_settings(tmp_path), **FAKES)
    assert isinstance(pinned.provider, ScriptedProvider)
    pinned.store.close()


def test_model_settings_api_never_reveals_the_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SHUNYA_MODEL_PROVIDER", raising=False)
    settings = _settings(tmp_path)
    settings.api_token = "owner-token"
    auth = {"Authorization": "Bearer owner-token"}
    with TestClient(create_app(Studio(settings, **FAKES))) as client:
        assert client.get("/settings/model").status_code == 401  # owner only
        assert client.post("/settings/model", json={"api_key": SECRET}).status_code == 401
        before = client.get("/settings/model", headers=auth).json()
        assert before["provider"] == "scripted" and before["key_set"] is False and before["max_spend_usd"] == 25.0
        assert client.post("/settings/model", headers=auth, json={"provider": "anthropic"}).status_code == 400  # no key yet

        saved = client.post("/settings/model", headers=auth, json={"api_key": SECRET, "max_spend_usd": 5})
        assert saved.status_code == 200
        body = saved.json()
        assert body["provider"] == "anthropic" and body["key_set"] is True and body["key_hint"] == "...WXYZ" and body["max_spend_usd"] == 5
        studio = client.app.state.studio
        assert isinstance(studio.provider, AnthropicProvider) and studio.runner.provider is studio.provider

        # the key is write-only: not in any response the UI or an agent could read
        for path in ("/settings/model", "/studio/state", "/system", "/health", "/agents", "/events?recent=true"):
            assert SECRET not in client.get(path, headers=auth).text, path
        assert SECRET not in saved.text
        assert client.get("/studio/state", headers=auth).json()["provider"] == "anthropic"

        removed = client.post("/settings/model", headers=auth, json={"api_key": "", "provider": "scripted"}).json()
        assert removed["provider"] == "scripted" and removed["key_set"] is False
        assert isinstance(studio.provider, ScriptedProvider)
    assert SECRET not in (settings.data_dir / "secrets.json").read_text(encoding="utf-8")
    log = settings.logs_dir / "studio.log"
    assert not log.exists() or SECRET not in log.read_text(encoding="utf-8")


class _Report(BaseModel):
    summary: str


class _PricedProvider(IModelProvider):
    """Behaves like a real, billed model: every call costs money and it never finishes on its own."""

    name = "priced"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system, messages, tools, config, agent_id="") -> ModelResponse:
        self.calls += 1
        call = ToolCallRequest(id=f"c{self.calls}", name="list_dir", arguments={"path": "Source", "depth": 1 + self.calls % 5})
        return ModelResponse(tool_calls=[call], stop_reason="tool_use", model="claude-opus-5-5", usage=Usage(input_tokens=200_000, output_tokens=10_000))  # $1.00 per call

    async def structured_generate(self, **_):
        raise NotImplementedError

    async def stream(self, **_):
        yield ""


async def test_spending_cap_stops_model_calls_until_the_owner_raises_it(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = _settings(tmp_path, model_provider="scripted")
    settings.max_spend_usd = 3.0
    provider = _PricedProvider()
    studio = await Studio(settings, provider=provider, **FAKES).start()
    agent = studio.registry.get("gameplay_programmer_01").model_copy(update={"cost_budget": 1000.0, "token_budget": 10**12, "max_iterations": 1000, "max_tool_calls": 1000})

    async def run():
        sandbox = WorkspaceSandbox(Path(settings.game_repo), isolated=True)
        return await studio.runner.run(RunRequest(agent=agent, purpose="t", brief="x", output_model=_Report, control=RunControl(), sandbox=sandbox))

    first = await run()
    assert first.run.status == RunStatus.BUDGET_EXCEEDED and "spending cap ($3.00)" in first.run.error
    assert provider.calls == 3 and studio.spend.spent_usd == 3.0 and studio.spend.exhausted  # stopped at the cap, not after it

    second = await run()  # nothing more is spent while the cap is reached
    assert second.run.status == RunStatus.BUDGET_EXCEEDED and provider.calls == 3

    studio.configure_model(max_spend_usd=5.0)  # the owner raises the cap
    third = await run()
    assert provider.calls == 5 and studio.spend.spent_usd == 5.0 and third.run.status == RunStatus.BUDGET_EXCEEDED
    assert studio.model_settings()["remaining_usd"] == 0.0
    await studio.stop()

    # the meter survives a restart: it is rebuilt from the cost ledger
    reborn = Studio(_settings(tmp_path, model_provider="scripted"), provider=_PricedProvider(), **FAKES)
    assert reborn.spend.spent_usd == 5.0
    reborn.store.close()
