"""Task state machine (spec 9) and the task service that enforces it.

The workflow (an LLM-free orchestrator) is the only caller that moves tasks; transitions
are validated here deterministically and every one produces a TASK_STATUS_CHANGED event.
"""

from __future__ import annotations

from shunya.core.interfaces import IEventBus, ITaskRepository
from shunya.core.persistence import Store
from shunya.shared.schemas import (
    TERMINAL_TASK_STATUSES,
    Event,
    EventType,
    Task,
    TaskStatus,
    TaskTransition,
    utcnow,
)

S = TaskStatus

TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    S.BACKLOG: {S.PLANNED},
    S.PLANNED: {S.ASSIGNED, S.IN_PROGRESS, S.DONE, S.BLOCKED},  # an epic goes PLANNED -> IN_PROGRESS -> DONE
    S.ASSIGNED: {S.IN_PROGRESS, S.BLOCKED},
    S.IN_PROGRESS: {S.REVIEW, S.BLOCKED, S.DONE, S.FAILED},
    S.REVIEW: {S.BUILD, S.CHANGES_REQUESTED, S.BLOCKED},
    S.CHANGES_REQUESTED: {S.IN_PROGRESS, S.BLOCKED},
    S.BUILD: {S.QA, S.FAILED, S.BLOCKED},
    S.QA: {S.ACCEPTED, S.FAILED, S.BLOCKED},
    S.FAILED: {S.BUG_CREATED, S.BLOCKED},
    S.BUG_CREATED: {S.IN_PROGRESS, S.BLOCKED},
    S.ACCEPTED: {S.AWAITING_APPROVAL, S.DONE},
    S.AWAITING_APPROVAL: {S.DONE, S.REJECTED, S.BLOCKED},
    S.REJECTED: {S.IN_PROGRESS, S.BLOCKED},
    S.BLOCKED: {S.IN_PROGRESS, S.ASSIGNED, S.PLANNED, S.BACKLOG},
    S.DONE: set(),
    S.CANCELLED: set(),
}

# Statuses in which a task's pipeline is actively executing (resumed after a restart).
ACTIVE_STATUSES = {
    S.BACKLOG,
    S.PLANNED,
    S.ASSIGNED,
    S.IN_PROGRESS,
    S.REVIEW,
    S.CHANGES_REQUESTED,
    S.BUILD,
    S.QA,
    S.FAILED,
    S.BUG_CREATED,
    S.ACCEPTED,
    S.REJECTED,
}


class InvalidTransition(Exception):
    pass


def can_transition(src: TaskStatus, dst: TaskStatus) -> bool:
    if dst == S.CANCELLED:
        return src not in TERMINAL_TASK_STATUSES
    if dst == S.BLOCKED:  # escalation to a human is possible from any live state
        return src not in TERMINAL_TASK_STATUSES and src != S.BLOCKED
    return dst in TRANSITIONS.get(src, set())


class SqlTaskRepository(ITaskRepository):
    def __init__(self, store: Store):
        self._store = store

    def get(self, task_id: str) -> Task | None:
        return self._store.tasks.get(task_id)

    def save(self, task: Task) -> Task:
        task.updated_at = utcnow()
        return self._store.tasks.put(task)

    def list(self, *, status: TaskStatus | None = None, parent_id: str | None = None) -> list[Task]:
        tasks = self._store.tasks.list(status=str(status) if status else None, limit=5000)
        if parent_id is not None:
            tasks = [t for t in tasks if t.parent_id == parent_id]
        return tasks

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{self._store.next_counter(f'task:{prefix}')}"


class TaskService:
    def __init__(self, repo: ITaskRepository, bus: IEventBus):
        self.repo = repo
        self.bus = bus

    async def create(self, task: Task) -> Task:
        self.repo.save(task)
        await self.bus.publish(
            Event(
                type=EventType.TASK_CREATED,
                task_id=task.id,
                trace_id=task.trace_id,
                agent_id=task.created_by,
                payload={"title": task.title, "type": task.type, "status": task.status, "parent_id": task.parent_id},
            )
        )
        return task

    async def transition(self, task: Task, to: TaskStatus, *, actor: str, reason: str = "") -> Task:
        src = task.status
        if src == to:
            return task
        if not can_transition(src, to):
            raise InvalidTransition(f"{task.id}: {src} -> {to} is not allowed")
        task.status = to
        task.history.append(TaskTransition(from_status=src, to_status=to, actor=actor, reason=reason))
        self.repo.save(task)
        await self.bus.publish(
            Event(
                type=EventType.TASK_STATUS_CHANGED,
                task_id=task.id,
                trace_id=task.trace_id,
                agent_id=actor,
                payload={"from": src, "to": to, "reason": reason, "title": task.title},
            )
        )
        if to == S.IN_PROGRESS and src in (S.ASSIGNED, S.PLANNED):
            await self.bus.publish(Event(type=EventType.TASK_STARTED, task_id=task.id, trace_id=task.trace_id, agent_id=task.owner))
        elif to == S.DONE:
            await self.bus.publish(Event(type=EventType.TASK_COMPLETED, task_id=task.id, trace_id=task.trace_id, agent_id=task.owner))
        elif to in (S.FAILED, S.BLOCKED):
            await self.bus.publish(
                Event(type=EventType.TASK_FAILED, task_id=task.id, trace_id=task.trace_id, agent_id=task.owner, payload={"status": to, "reason": reason})
            )
        return task

    async def assign(self, task: Task, agent_id: str, *, actor: str) -> Task:
        task.owner = agent_id
        self.repo.save(task)
        await self.bus.publish(
            Event(type=EventType.TASK_ASSIGNED, task_id=task.id, trace_id=task.trace_id, agent_id=agent_id, payload={"by": actor})
        )
        if task.status in (S.PLANNED, S.BLOCKED):
            await self.transition(task, S.ASSIGNED, actor=actor)
        return task

    def save(self, task: Task) -> Task:
        return self.repo.save(task)
