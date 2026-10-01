"""Agent registry (spec 5, 7): employees are YAML definitions, not permanently running processes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shunya.core.interfaces import IEventBus
from shunya.core.persistence import Store
from shunya.shared.schemas import AgentProfile, AgentState, AgentStatus, Event, EventType, utcnow


KEEP: Any = object()  # sentinel: leave the field unchanged


class AgentRegistry:
    def __init__(self, agents_dir: Path):
        self.agents_dir = agents_dir
        self._profiles: dict[str, AgentProfile] = {}

    def load(self) -> "AgentRegistry":
        self._profiles = {}
        for path in sorted(self.agents_dir.rglob("*.yaml")):
            docs = yaml.safe_load(path.read_text(encoding="utf-8"))
            for doc in docs if isinstance(docs, list) else [docs]:
                if not doc:
                    continue
                doc.setdefault("department", path.parent.name)
                profile = AgentProfile.model_validate(doc)
                if profile.id in self._profiles:
                    raise ValueError(f"duplicate agent id {profile.id} in {path}")
                self._profiles[profile.id] = profile
        return self

    def add(self, profile: AgentProfile) -> None:
        self._profiles[profile.id] = profile

    def get(self, agent_id: str) -> AgentProfile | None:
        return self._profiles.get(agent_id)

    def all(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def with_capability(self, capability: str) -> list[AgentProfile]:
        return [p for p in self._profiles.values() if p.enabled and p.capability == capability]


class AgentStatusService:
    """Authoritative live state of each employee; the 2.5D office renders exactly this."""

    def __init__(self, store: Store, bus: IEventBus, registry: AgentRegistry):
        self.store = store
        self.bus = bus
        self.registry = registry

    async def bootstrap(self) -> None:
        """Create status rows for new agents; after a restart nobody is mid-action."""
        for p in self.registry.all():
            status = self.store.agents.get(p.id)
            if status is None:
                status = AgentStatus(id=p.id, state=AgentState.IDLE if p.enabled else AgentState.OFFLINE)
                self.store.agents.put(status)
                await self.bus.publish(Event(type=EventType.AGENT_CREATED, agent_id=p.id, payload={"name": p.name, "role": p.role, "department": p.department}))
            else:
                target = AgentState.IDLE if p.enabled else AgentState.OFFLINE
                keep = status.state in (AgentState.WAITING_APPROVAL,) and p.enabled
                if not keep and (status.state != target or status.task_id or status.paused):
                    status.state, status.task_id, status.run_id, status.current_action, status.location, status.paused = target, None, None, "", "desk", False
                    status.updated_at = utcnow()
                    self.store.agents.put(status)

    def get(self, agent_id: str) -> AgentStatus:
        return self.store.agents.get(agent_id) or AgentStatus(id=agent_id)

    def all(self) -> list[AgentStatus]:
        return self.store.agents.list(limit=1000)

    async def set(
        self,
        agent_id: str,
        state: AgentState,
        *,
        action: str | None = None,
        task_id: Any = KEEP,
        run_id: Any = KEEP,
        location: str | None = None,
        trace_id: str | None = None,
    ) -> AgentStatus:
        status = self.get(agent_id)
        prev_state, prev_action, prev_loc = status.state, status.current_action, status.location
        if status.state != state:
            status.since = utcnow()
        status.state = state
        if action is not None:
            status.current_action = action
        if task_id is not KEEP:
            status.task_id = task_id
        if run_id is not KEEP:
            status.run_id = run_id
        if location is not None:
            status.location = location
        status.updated_at = utcnow()
        self.store.agents.put(status)
        if (prev_state, prev_action, prev_loc) != (status.state, status.current_action, status.location):
            await self.bus.publish(
                Event(
                    type=EventType.AGENT_STATUS_CHANGED,
                    agent_id=agent_id,
                    task_id=status.task_id,
                    run_id=status.run_id,
                    trace_id=trace_id,
                    payload={"from": prev_state, "to": state, "action": status.current_action, "location": status.location},
                )
            )
        return status

    async def set_paused(self, agent_id: str, paused: bool) -> AgentStatus:
        status = self.get(agent_id)
        status.paused = paused
        status.updated_at = utcnow()
        self.store.agents.put(status)
        await self.bus.publish(
            Event(type=EventType.AGENT_WAITING if paused else EventType.AGENT_STARTED, agent_id=agent_id, task_id=status.task_id, payload={"paused": paused})
        )
        return status
