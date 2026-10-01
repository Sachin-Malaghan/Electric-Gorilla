"""Deterministic provider for tests, CI and offline demos.

A script is a function of the conversation so far that returns the next model turn.
Because it is a pure function of its inputs, runs are exactly reproducible: the same
pipeline replays the same tool calls, which is how the runtime, permissions, budgets and
workflow are tested without spending money. It never pretends to be a real model -
responses are tagged model="scripted-demo" and cost nothing.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from shunya.core.interfaces import IModelProvider
from shunya.core.models.base import ChatMessage, ModelProviderError, ModelResponse, ToolCallRequest, ToolSpec, Usage
from shunya.shared.schemas import ModelConfig

_ids = itertools.count(1)


@dataclass
class ToolExchange:
    name: str
    arguments: dict[str, Any]
    result: str
    is_error: bool


@dataclass
class ScriptContext:
    agent_id: str
    system: str
    messages: list[ChatMessage]
    tools: list[ToolSpec]
    exchanges: list[ToolExchange] = field(default_factory=list)

    @property
    def brief(self) -> str:
        return self.messages[0].text if self.messages else ""

    @property
    def turn(self) -> int:
        return sum(1 for m in self.messages if m.role == "assistant")

    def called(self, name: str) -> list[ToolExchange]:
        return [e for e in self.exchanges if e.name == name]

    def last(self, name: str | None = None) -> ToolExchange | None:
        for e in reversed(self.exchanges):
            if name is None or e.name == name:
                return e
        return None

    def section(self, title: str) -> str:
        """Text of a '## title' section in the brief."""
        m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", self.brief, re.S | re.M)
        return m.group(1).strip() if m else ""


Script = Callable[[ScriptContext], "ScriptStep"]


@dataclass
class ScriptStep:
    text: str = ""
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


def call(name: str, **arguments: Any) -> ScriptStep:
    return ScriptStep(calls=[(name, arguments)])


def calls(*items: tuple[str, dict[str, Any]], text: str = "") -> ScriptStep:
    return ScriptStep(text=text, calls=list(items))


def _exchanges(messages: list[ChatMessage]) -> list[ToolExchange]:
    pending: dict[str, ToolCallRequest] = {}
    out: list[ToolExchange] = []
    for m in messages:
        for tc in m.tool_calls:
            pending[tc.id] = tc
        for r in m.tool_results:
            tc = pending.get(r.tool_call_id)
            if tc:
                out.append(ToolExchange(tc.name, tc.arguments, r.content, r.is_error))
    return out


class ScriptedProvider(IModelProvider):
    name = "scripted"

    def __init__(self, scripts: dict[str, Script], *, step_delay: float = 0.0):
        """scripts: keyed by agent id, or by capability name (matched from the system prompt marker)."""
        self.scripts = scripts
        self.step_delay = step_delay

    def _script_for(self, agent_id: str, system: str) -> Script:
        if agent_id in self.scripts:
            return self.scripts[agent_id]
        m = re.search(r"\[capability:(\w+)\]", system)
        if m and m.group(1) in self.scripts:
            return self.scripts[m.group(1)]
        raise ModelProviderError(f"no script for agent '{agent_id}'")

    async def generate(self, *, system, messages, tools, config, agent_id="") -> ModelResponse:
        if self.step_delay:
            await asyncio.sleep(self.step_delay)
        ctx = ScriptContext(agent_id, system, messages, tools, _exchanges(messages))
        step = self._script_for(agent_id, system)(ctx)
        tool_calls = [ToolCallRequest(id=f"scripted_{next(_ids)}", name=n, arguments=a) for n, a in step.calls]
        prompt_chars = len(system) + sum(len(m.text) + sum(len(r.content) for r in m.tool_results) for m in messages)
        out_chars = len(step.text) + sum(len(json.dumps(a)) for _, a in step.calls)
        return ModelResponse(
            text=step.text,
            tool_calls=tool_calls,
            stop_reason="tool_use" if tool_calls else "end_turn",
            usage=Usage(input_tokens=prompt_chars // 4, output_tokens=max(1, out_chars // 4)),
            model="scripted-demo",
        )

    async def structured_generate(self, *, system, messages, schema, config, agent_id=""):
        resp = await self.generate(system=system, messages=messages, tools=[], config=config, agent_id=agent_id)
        return json.loads(resp.text or "{}"), resp

    async def stream(self, *, system, messages, config: ModelConfig, agent_id="") -> AsyncIterator[str]:  # type: ignore[override]
        resp = await self.generate(system=system, messages=messages, tools=[], config=config, agent_id=agent_id)
        yield resp.text
