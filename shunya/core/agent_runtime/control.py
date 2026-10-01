"""Pause / cancel control for runs (spec 6: cancellation; spec 49: user can pause/cancel)."""

from __future__ import annotations

import asyncio


class RunCancelled(Exception):
    pass


class RunControl:
    def __init__(self) -> None:
        self._cancelled = asyncio.Event()
        self._running = asyncio.Event()
        self._running.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._running.set()  # wake a paused waiter so it can observe the cancel

    def pause(self) -> None:
        if not self._cancelled.is_set():
            self._running.clear()

    def resume(self) -> None:
        self._running.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    async def checkpoint(self) -> None:
        """Called between steps: blocks while paused, raises once cancelled."""
        if self._cancelled.is_set():
            raise RunCancelled()
        if not self._running.is_set():
            await self._running.wait()
            if self._cancelled.is_set():
                raise RunCancelled()


class CompositeControl(RunControl):
    """A run obeys both its task's control and its agent's control."""

    def __init__(self, *controls: RunControl):
        super().__init__()
        self._controls = controls

    @property
    def cancelled(self) -> bool:
        return any(c.cancelled for c in self._controls)

    @property
    def paused(self) -> bool:
        return any(c.paused for c in self._controls)

    async def checkpoint(self) -> None:
        for c in self._controls:
            await c.checkpoint()
        # a control earlier in the list may have been paused while we waited on a later one
        if any(c.paused for c in self._controls):
            await self.checkpoint()


class ControlRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, RunControl] = {}
        self._agents: dict[str, RunControl] = {}

    def task(self, task_id: str) -> RunControl:
        return self._tasks.setdefault(task_id, RunControl())

    def agent(self, agent_id: str) -> RunControl:
        return self._agents.setdefault(agent_id, RunControl())

    def for_run(self, task_id: str | None, agent_id: str) -> RunControl:
        controls = [self.agent(agent_id)]
        if task_id:
            controls.insert(0, self.task(task_id))
        return CompositeControl(*controls)

    def reset_task(self, task_id: str) -> RunControl:
        self._tasks[task_id] = RunControl()
        return self._tasks[task_id]
