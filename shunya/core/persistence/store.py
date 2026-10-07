"""Structured store - the source of truth (spec 24).

PostgreSQL in deployment (DATABASE_URL=postgresql+psycopg://...), SQLite by default so the
studio runs with nothing installed. Each entity has its own table with indexed lookup
columns and the full Pydantic document as JSON; the event log is append-only with a
monotonically increasing sequence number, which is what restart recovery and WebSocket
catch-up replay from.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    event,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from shunya.shared import schemas as s

T = TypeVar("T", bound=BaseModel)

metadata = MetaData()


def _entity_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        Column("id", String(64), primary_key=True),
        Column("task_id", String(64), index=True, nullable=True),
        Column("agent_id", String(64), index=True, nullable=True),
        Column("status", String(32), index=True, nullable=True),
        Column("created_at", DateTime(timezone=True), index=True),
        Column("updated_at", DateTime(timezone=True)),
        Column("data", JSON, nullable=False),
    )


ENTITY_TABLES = {
    name: _entity_table(name)
    for name in (
        "projects",
        "games",
        "agents",
        "tasks",
        "agent_runs",
        "tool_calls",
        "messages",
        "artifacts",
        "builds",
        "tests",
        "bugs",
        "approvals",
        "meetings",
        "memories",
        "cost_records",
        "knowledge_chunks",
    )
}

events_table = Table(
    "events",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), unique=True),
    Column("type", String(48), index=True),
    Column("task_id", String(64), index=True, nullable=True),
    Column("agent_id", String(64), index=True, nullable=True),
    Column("trace_id", String(64), index=True, nullable=True),
    Column("timestamp", DateTime(timezone=True), index=True),
    Column("data", JSON, nullable=False),
)

counters_table = Table(
    "counters",
    metadata,
    Column("name", String(64), primary_key=True),
    Column("value", Integer, nullable=False),
)


class Repository(Generic[T]):
    def __init__(self, engine: Engine, table: Table, model: type[T], lock: threading.RLock):
        self._engine = engine
        self._table = table
        self._model = model
        self._lock = lock

    @staticmethod
    def _columns(obj: BaseModel) -> dict[str, Any]:
        def attr(*names: str) -> Any:
            for n in names:
                v = getattr(obj, n, None)
                if v is not None:
                    return str(v) if not isinstance(v, datetime) else v
            return None

        created = attr("created_at", "started_at", "timestamp", "since") or s.utcnow()
        return {
            "id": obj.id,  # type: ignore[attr-defined]
            "task_id": attr("task_id"),
            "agent_id": attr("agent_id", "owner", "creator", "sender"),
            "status": attr("status", "state"),
            "created_at": created,
            "updated_at": s.utcnow(),
            "data": obj.model_dump(mode="json"),
        }

    def put(self, obj: T) -> T:
        row = self._columns(obj)
        with self._lock, self._engine.begin() as conn:
            exists = conn.execute(select(self._table.c.id).where(self._table.c.id == row["id"])).first()
            if exists:
                row.pop("created_at")
                conn.execute(update(self._table).where(self._table.c.id == row["id"]).values(**row))
            else:
                conn.execute(insert(self._table).values(**row))
        return obj

    def get(self, obj_id: str) -> T | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(self._table.c.data).where(self._table.c.id == obj_id)).first()
        return self._model.model_validate(row[0]) if row else None

    def list(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: str | list[str] | None = None,
        limit: int = 500,
        newest_first: bool = False,
    ) -> list[T]:
        q = select(self._table.c.data)
        if task_id is not None:
            q = q.where(self._table.c.task_id == task_id)
        if agent_id is not None:
            q = q.where(self._table.c.agent_id == agent_id)
        if status is not None:
            statuses = [status] if isinstance(status, str) else list(status)
            q = q.where(self._table.c.status.in_([str(x) for x in statuses]))
        order = self._table.c.created_at.desc() if newest_first else self._table.c.created_at.asc()
        q = q.order_by(order).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(q).all()
        return [self._model.model_validate(r[0]) for r in rows]

    def delete(self, obj_id: str) -> None:
        with self._lock, self._engine.begin() as conn:
            conn.execute(delete(self._table).where(self._table.c.id == obj_id))

    def count(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(self._table)).scalar_one()


class EventLog:
    def __init__(self, engine: Engine, lock: threading.RLock):
        self._engine = engine
        self._lock = lock

    def append(self, event: s.Event) -> s.Event:
        with self._lock, self._engine.begin() as conn:
            result = conn.execute(
                insert(events_table).values(
                    id=event.id,
                    type=str(event.type),
                    task_id=event.task_id,
                    agent_id=event.agent_id,
                    trace_id=event.trace_id,
                    timestamp=event.timestamp,
                    data={},
                )
            )
            seq = result.inserted_primary_key[0]
            event.seq = int(seq)
            conn.execute(
                update(events_table).where(events_table.c.seq == seq).values(data=event.model_dump(mode="json"))
            )
        return event

    def since(self, seq: int = 0, *, limit: int = 1000, task_id: str | None = None, agent_id: str | None = None) -> list[s.Event]:
        q = select(events_table.c.data).where(events_table.c.seq > seq)
        if task_id:
            q = q.where(events_table.c.task_id == task_id)
        if agent_id:
            q = q.where(events_table.c.agent_id == agent_id)
        q = q.order_by(events_table.c.seq.asc()).limit(limit)
        with self._engine.connect() as conn:
            return [s.Event.model_validate(r[0]) for r in conn.execute(q).all()]

    def recent(self, limit: int = 200, *, task_id: str | None = None, agent_id: str | None = None) -> list[s.Event]:
        q = select(events_table.c.data)
        if task_id:
            q = q.where(events_table.c.task_id == task_id)
        if agent_id:
            q = q.where(events_table.c.agent_id == agent_id)
        q = q.order_by(events_table.c.seq.desc()).limit(limit)
        with self._engine.connect() as conn:
            rows = [s.Event.model_validate(r[0]) for r in conn.execute(q).all()]
        return list(reversed(rows))

    def last_seq(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(select(func.coalesce(func.max(events_table.c.seq), 0))).scalar_one())


class Store:
    def __init__(self, url: str):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi_conn, _record) -> None:
                # WAL + NORMAL: durable across application crashes, without an fsync per event
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        else:
            self.engine = create_engine(url, pool_pre_ping=True)
        metadata.create_all(self.engine)
        self._lock = threading.RLock()
        t = ENTITY_TABLES

        def repo(name: str, model: type[T]) -> Repository[T]:
            return Repository(self.engine, t[name], model, self._lock)

        self.projects = repo("projects", s.Project)
        self.games = repo("games", s.Game)
        self.agents = repo("agents", s.AgentStatus)
        self.tasks = repo("tasks", s.Task)
        self.runs = repo("agent_runs", s.AgentRun)
        self.tool_calls = repo("tool_calls", s.ToolCallRecord)
        self.messages = repo("messages", s.AgentMessage)
        self.artifacts = repo("artifacts", s.Artifact)
        self.builds = repo("builds", s.BuildRecord)
        self.tests = repo("tests", s.TestRunRecord)
        self.bugs = repo("bugs", s.Bug)
        self.approvals = repo("approvals", s.Approval)
        self.meetings = repo("meetings", s.CollaborationSession)
        self.memories = repo("memories", s.MemoryRecord)
        self.cost_records = repo("cost_records", s.CostRecord)
        self.knowledge_chunks = repo("knowledge_chunks", s.KnowledgeChunk)
        self.events = EventLog(self.engine, self._lock)

    def next_counter(self, name: str) -> int:
        with self._lock, self.engine.begin() as conn:
            row = conn.execute(select(counters_table.c.value).where(counters_table.c.name == name)).first()
            value = (row[0] if row else 0) + 1
            if row:
                conn.execute(update(counters_table).where(counters_table.c.name == name).values(value=value))
            else:
                conn.execute(insert(counters_table).values(name=name, value=value))
        return value

    def close(self) -> None:
        self.engine.dispose()
