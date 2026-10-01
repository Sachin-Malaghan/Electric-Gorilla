"""Event bus (spec 11).

Every meaningful state change is persisted to the append-only event log first (so it
survives restarts and late WebSocket clients can catch up by sequence number) and then
fanned out to live subscribers. InMemoryEventBus serves one process; RedisEventBus fans
out across processes (API + workers) through Redis Pub/Sub and mirrors into a Redis
Stream. Kafka is deliberately not used (spec 11 / 45).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from shunya.core.interfaces import IEventBus
from shunya.core.persistence import EventLog
from shunya.shared.schemas import Event

log = logging.getLogger(__name__)


class InMemoryEventBus(IEventBus):
    def __init__(self, event_log: EventLog | None = None, queue_size: int = 2000):
        self._log = event_log
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._queue_size = queue_size

    async def publish(self, event: Event) -> Event:
        if self._log is not None:
            event = self._log.append(event)
        self._fan_out(event)
        return event

    def _fan_out(self, event: Event) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # A slow consumer must not stall the studio; it can resync from the log by seq.
                log.warning("event subscriber queue full; dropping event %s", event.seq)

    async def subscribe(self) -> AsyncIterator[Event]:  # type: ignore[override]
        q: asyncio.Queue[Event] = asyncio.Queue(self._queue_size)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class RedisEventBus(InMemoryEventBus):
    """Persists locally, then publishes to Redis so other processes' subscribers see it."""

    CHANNEL = "shunya:events"
    STREAM = "shunya:events:stream"

    def __init__(self, url: str, event_log: EventLog | None = None):
        super().__init__(event_log)
        import redis.asyncio as redis  # optional dependency

        self._redis = redis.from_url(url)
        self._listener: asyncio.Task | None = None

    async def start(self) -> None:
        if self._listener is None:
            self._listener = asyncio.create_task(self._listen())

    async def publish(self, event: Event) -> Event:
        if self._log is not None:
            event = self._log.append(event)
        data = event.model_dump_json()
        await self._redis.xadd(self.STREAM, {"event": data}, maxlen=100_000, approximate=True)
        await self._redis.publish(self.CHANNEL, data)
        return event

    async def _listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                self._fan_out(Event.model_validate(json.loads(message["data"])))
            except Exception:  # noqa: BLE001
                log.exception("bad event on redis channel")
