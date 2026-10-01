"""Studio API (spec 26): REST for commands and queries, /ws/studio for the live event stream.

The 2.5D client is a projection of this API: it loads /studio/state once, then applies
events from the WebSocket. It never invents activity.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shunya.bridge import BridgeUnavailable
from shunya.bridge.client import EDITOR_COMMANDS, READ_ROUTES, RUNTIME_COMMANDS
from shunya.config import Settings
from shunya.core.models.pricing import PRICES
from shunya.knowledge import HybridRetriever
from shunya.shared.schemas import Priority, TaskStatus
from shunya.studio import Studio

log = logging.getLogger(__name__)


class FeatureRequest(BaseModel):
    request: str = Field(min_length=3, max_length=8000)
    priority: Priority = Priority.MEDIUM


class Decision(BaseModel):
    comment: str = ""
    decided_by: str = "studio_owner"
    rework: bool = False


class RetryBody(BaseModel):
    note: str = ""


class UnrealCommand(BaseModel):
    command: str
    args: dict[str, Any] = Field(default_factory=dict)
    scope: str = "editor"


def create_app(studio: Studio | None = None, settings: Settings | None = None) -> FastAPI:
    owned = studio is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.studio = studio or Studio(settings)
        await app.state.studio.start()
        try:
            yield
        finally:
            if owned:
                await app.state.studio.stop()

    app = FastAPI(title="Shunya Studio AI", version="0.1.0", lifespan=lifespan)

    def st() -> Studio:
        return app.state.studio

    def dump(items) -> list[dict]:
        return [i.model_dump(mode="json") for i in items]

    def must(obj, what: str):
        if obj is None:
            raise HTTPException(404, f"{what} not found")
        return obj

    # ------------------------------------------------------------------ studio / projects

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/studio/state")
    async def studio_state():
        return st().snapshot()

    @app.get("/projects")
    async def projects():
        return dump(st().store.projects.list())

    # ------------------------------------------------------------------ agents

    @app.get("/agents")
    async def agents():
        return [st().agent_view(p.id) for p in st().registry.all()]

    @app.get("/agents/{agent_id}")
    async def agent(agent_id: str):
        s = st()
        view = must(s.agent_view(agent_id), "agent")
        profile = s.registry.get(agent_id)
        task = s.store.tasks.get(view["task_id"]) if view["task_id"] else None
        runs = s.store.runs.list(agent_id=agent_id, limit=15, newest_first=True)
        calls = s.store.tool_calls.list(agent_id=agent_id, limit=60, newest_first=True)
        memories = [m for m in s.store.memories.list(limit=400, newest_first=True) if m.agent_id == agent_id][:12]
        return {
            **view,
            "profile": profile.model_dump(mode="json"),
            "task": task.model_dump(mode="json", exclude={"history"}) if task else None,
            "runs": dump(runs),
            "activity": [
                {"time": c.timestamp.isoformat(), "tool": c.tool, "ok": c.ok, "summary": c.summary, "latency_ms": c.latency_ms, "error": c.error}
                for c in calls
            ],
            "memory": dump(memories),
            "totals": {
                "runs": len(runs),
                "cost_usd": round(sum(r.cost_usd for r in runs), 4),
                "tokens": sum(r.input_tokens + r.output_tokens for r in runs),
            },
        }

    @app.post("/agents/{agent_id}/pause")
    async def pause_agent(agent_id: str):
        s = st()
        must(s.registry.get(agent_id), "agent")
        s.controls.agent(agent_id).pause()
        return (await s.statuses.set_paused(agent_id, True)).model_dump(mode="json")

    @app.post("/agents/{agent_id}/resume")
    async def resume_agent(agent_id: str):
        s = st()
        must(s.registry.get(agent_id), "agent")
        s.controls.agent(agent_id).resume()
        return (await s.statuses.set_paused(agent_id, False)).model_dump(mode="json")

    @app.get("/agents/{agent_id}/report")
    async def agent_report(agent_id: str):
        """REQUEST REPORT: a factual status report assembled from records (no LLM call)."""
        s = st()
        view = must(s.agent_view(agent_id), "agent")
        run = s.store.runs.get(view["run_id"]) if view["run_id"] else None
        calls = s.store.tool_calls.list(agent_id=agent_id, limit=8, newest_first=True)
        lines = [f"{view['name']} ({view['role']}) - {view['state']}"]
        if view["task_id"]:
            task = s.store.tasks.get(view["task_id"])
            lines.append(f"Task: {view['task_id']} - {task.title if task else ''} [{task.status if task else '?'}]")
        if view["current_action"]:
            lines.append(f"Current action: {view['current_action']}")
        if run:
            lines.append(f"Run {run.id}: {run.iterations} iterations, {run.tool_calls} tool calls, {run.input_tokens + run.output_tokens} tokens, ${run.cost_usd:.4f}")
            lines.append(f"Files inspected: {len(run.files_inspected)}; modified: {', '.join(run.files_modified) or 'none'}")
        if calls:
            lines.append("Recent activity:")
            lines += [f"  {c.timestamp.strftime('%H:%M:%S')} {c.summary}" for c in reversed(calls)]
        return {"agent_id": agent_id, "report": "\n".join(lines)}

    # ------------------------------------------------------------------ tasks

    @app.get("/tasks")
    async def tasks(status: TaskStatus | None = None, parent_id: str | None = None):
        items = st().store.tasks.list(status=str(status) if status else None, limit=2000)
        if parent_id:
            items = [t for t in items if t.parent_id == parent_id]
        return [t.model_dump(mode="json", exclude={"history"}) for t in items]

    @app.post("/tasks", status_code=201)
    async def create_feature(body: FeatureRequest):
        task = await st().orchestrator.submit_feature(body.request, priority=body.priority)
        return task.model_dump(mode="json")

    @app.get("/tasks/{task_id}")
    async def task(task_id: str):
        s = st()
        t = must(s.store.tasks.get(task_id), "task")
        return {
            **t.model_dump(mode="json"),
            "children": [c.model_dump(mode="json", exclude={"history"}) for c in s.store.tasks.list(limit=2000) if c.parent_id == task_id],
            "runs": dump(s.store.runs.list(task_id=task_id)),
            "builds": dump(s.store.builds.list(task_id=task_id)),
            "tests": dump(s.store.tests.list(task_id=task_id)),
            "bugs": dump(s.store.bugs.list(task_id=task_id)),
            "messages": dump(s.store.messages.list(task_id=task_id)),
            "artifacts": dump(s.store.artifacts.list(task_id=task_id)),
            "approvals": dump(s.store.approvals.list(task_id=task_id)),
            "running": s.orchestrator.is_running(task_id),
        }

    async def _control(task_id: str, action: str, **kwargs):
        s = st()
        must(s.store.tasks.get(task_id), "task")
        try:
            result = await getattr(s.orchestrator, action)(task_id, **kwargs)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        return result.model_dump(mode="json", exclude={"history"})

    @app.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        return await _control(task_id, "cancel")

    @app.post("/tasks/{task_id}/pause")
    async def pause_task(task_id: str):
        return await _control(task_id, "pause")

    @app.post("/tasks/{task_id}/resume")
    async def resume_task(task_id: str):
        return await _control(task_id, "resume")

    @app.post("/tasks/{task_id}/retry")
    async def retry_task(task_id: str, body: RetryBody | None = None):
        return await _control(task_id, "retry", note=(body.note if body else ""))

    @app.get("/tasks/{task_id}/diff", response_class=PlainTextResponse)
    async def task_diff(task_id: str):
        s = st()
        t = must(s.store.tasks.get(task_id), "task")
        patch_id = t.result.get("patch_artifact_id")
        patches = [a for a in s.store.artifacts.list(task_id=task_id) if a.type == "CodePatch"]
        art_id = patches[-1].id if patches else patch_id
        if not art_id:
            return ""
        return s.artifacts.read_text(art_id)

    # ------------------------------------------------------------------ runs / builds / tests / bugs / traces

    @app.get("/runs")
    async def runs(task_id: str | None = None, agent_id: str | None = None, limit: int = Query(100, le=1000)):
        return dump(st().store.runs.list(task_id=task_id, agent_id=agent_id, limit=limit, newest_first=True))

    @app.get("/runs/{run_id}")
    async def run(run_id: str):
        s = st()
        r = must(s.store.runs.get(run_id), "run")
        calls = [c for c in s.store.tool_calls.list(agent_id=r.agent_id, limit=2000) if c.run_id == run_id]
        return {**r.model_dump(mode="json"), "tool_calls": dump(calls)}

    @app.get("/builds")
    async def builds(task_id: str | None = None, limit: int = Query(50, le=500)):
        return dump(st().store.builds.list(task_id=task_id, limit=limit, newest_first=True))

    @app.get("/tests")
    async def tests(task_id: str | None = None, limit: int = Query(50, le=500)):
        return dump(st().store.tests.list(task_id=task_id, limit=limit, newest_first=True))

    @app.get("/bugs")
    async def bugs(task_id: str | None = None):
        return dump(st().store.bugs.list(task_id=task_id, limit=500, newest_first=True))

    @app.get("/meetings")
    async def meetings(limit: int = Query(50, le=500)):
        return dump(st().store.meetings.list(limit=limit, newest_first=True))

    @app.get("/messages")
    async def messages(task_id: str | None = None, limit: int = Query(100, le=1000)):
        return dump(st().store.messages.list(task_id=task_id, limit=limit, newest_first=True))

    @app.get("/artifacts")
    async def artifacts(task_id: str | None = None, limit: int = Query(100, le=1000)):
        return dump(st().store.artifacts.list(task_id=task_id, limit=limit, newest_first=True))

    @app.get("/artifacts/{artifact_id}")
    async def artifact(artifact_id: str):
        s = st()
        art = must(s.artifacts.get(artifact_id), "artifact")
        media = art.content_type if art.content_type.startswith(("image/", "application/json")) else "text/plain; charset=utf-8"
        return Response(s.artifacts.read(artifact_id), media_type=media)

    @app.get("/traces/{trace_id}")
    async def trace(trace_id: str):
        """End-to-end trace (spec 31): every event, run and tool call under one trace id."""
        s = st()
        events = [e for e in s.store.events.since(0, limit=20000) if e.trace_id == trace_id]
        run_list = [r for r in s.store.runs.list(limit=5000) if r.trace_id == trace_id]
        calls = [c for c in s.store.tool_calls.list(limit=20000) if c.trace_id == trace_id]
        if not events and not run_list:
            raise HTTPException(404, "trace not found")
        return {
            "trace_id": trace_id,
            "cost_usd": round(sum(r.cost_usd for r in run_list), 6),
            "tokens": sum(r.input_tokens + r.output_tokens for r in run_list),
            "runs": [
                {**r.model_dump(mode="json", exclude={"report"}), "tool_calls": dump([c for c in calls if c.run_id == r.id])}
                for r in run_list
            ],
            "events": dump(events),
        }

    @app.get("/costs")
    async def costs():
        s = st()
        records = s.store.cost_records.list(limit=50000)
        by_agent: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for r in records:
            by_agent[r.agent_id] = by_agent.get(r.agent_id, 0.0) + r.cost_usd
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd
        return {
            "total_usd": round(sum(r.cost_usd for r in records), 6),
            "llm_calls": len(records),
            "by_agent": {k: round(v, 6) for k, v in sorted(by_agent.items())},
            "by_model": {k: round(v, 6) for k, v in sorted(by_model.items())},
            "prices_per_mtok": {m: {"input": p[0], "output": p[1]} for m, p in PRICES.items()},
        }

    # ------------------------------------------------------------------ approvals

    @app.get("/approvals")
    async def approvals(status: str | None = None):
        return dump(st().store.approvals.list(status=status, limit=500, newest_first=True))

    @app.get("/approvals/{approval_id}")
    async def approval(approval_id: str):
        s = st()
        a = must(s.store.approvals.get(approval_id), "approval")
        diff = s.artifacts.read_text(a.diff_artifact_id) if a.diff_artifact_id else ""
        return {**a.model_dump(mode="json"), "diff": diff}

    async def _decide(approval_id: str, granted: bool, body: Decision):
        try:
            a = await st().approvals.decide(approval_id, granted=granted, decided_by=body.decided_by, comment=body.comment, rework=body.rework)
        except KeyError:
            raise HTTPException(404, "approval not found") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        return a.model_dump(mode="json")

    @app.post("/approvals/{approval_id}/approve")
    async def approve(approval_id: str, body: Decision | None = None):
        return await _decide(approval_id, True, body or Decision())

    @app.post("/approvals/{approval_id}/reject")
    async def reject(approval_id: str, body: Decision | None = None):
        return await _decide(approval_id, False, body or Decision())

    # ------------------------------------------------------------------ events

    @app.get("/events")
    async def events(since: int = 0, limit: int = Query(500, le=5000), task_id: str | None = None, agent_id: str | None = None, recent: bool = False):
        log_ = st().store.events
        items = log_.recent(limit, task_id=task_id, agent_id=agent_id) if recent else log_.since(since, limit=limit, task_id=task_id, agent_id=agent_id)
        return dump(items)

    @app.websocket("/ws/studio")
    async def ws_studio(ws: WebSocket, since: int | None = None):
        await ws.accept()
        s = st()
        stream = s.bus.subscribe()
        # Subscribe before replaying so nothing published in between is lost; de-dupe by seq.
        pending = asyncio.ensure_future(stream.__anext__())
        last = since if since is not None else s.store.events.last_seq()
        try:
            await ws.send_json({"kind": "hello", "last_seq": s.store.events.last_seq()})
            if since is not None:
                for e in s.store.events.since(since, limit=5000):
                    await ws.send_json({"kind": "event", "event": e.model_dump(mode="json")})
                    last = max(last, e.seq)
            while True:
                event = await pending
                pending = asyncio.ensure_future(stream.__anext__())
                if event.seq and event.seq <= last:
                    continue
                last = max(last, event.seq)
                await ws.send_json({"kind": "event", "event": event.model_dump(mode="json")})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            pending.cancel()
            with contextlib.suppress(Exception):
                await stream.aclose()

    # ------------------------------------------------------------------ unreal / knowledge

    @app.get("/unreal/status")
    async def unreal_status():
        s = st()
        return {
            "engine_root": str(s.settings.engine_root) if s.settings.engine_root else None,
            "build_tools_available": s.settings.unreal_available,
            "game_repo": str(s.settings.game_repo),
            "editor_bridge": await s.bridge.status(),
        }

    @app.get("/unreal/query/{route}")
    async def unreal_query(route: str, name: str | None = None, class_name: str | None = None, path: str | None = None, limit: int | None = None):
        if route not in READ_ROUTES:
            raise HTTPException(404, "unknown route")
        params = {k: v for k, v in {"name": name, "class_name": class_name, "path": path, "limit": limit}.items() if v is not None}
        try:
            return await st().bridge.query(route, params)
        except BridgeUnavailable as e:
            raise HTTPException(503, str(e)) from None

    @app.post("/unreal/command")
    async def unreal_command(body: UnrealCommand):
        """Human-issued editor command (the studio owner has full authority; agents go through tools + permissions)."""
        if body.command not in EDITOR_COMMANDS | RUNTIME_COMMANDS:
            raise HTTPException(400, "unknown command")
        try:
            return await st().bridge.command(body.command, body.args, body.scope)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None
        except BridgeUnavailable as e:
            raise HTTPException(503, str(e)) from None

    @app.get("/knowledge/search")
    async def knowledge_search(q: str = Query(min_length=2), limit: int = Query(8, le=20)):
        s = st()
        results = await asyncio.to_thread(lambda: s.services.retriever_for(s.settings.game_repo).search(q, limit=limit))
        return {"query": q, "results": results, "rendered": HybridRetriever.render(results)}

    @app.get("/knowledge/graph")
    async def knowledge_graph(symbol: str):
        s = st()
        index = (await asyncio.to_thread(lambda: s.services.retriever_for(s.settings.game_repo))).index
        return {
            "symbols": [vars(x) for x in index.find_symbol(symbol)[:20]],
            "edges": [vars(e) for e in index.edges_of(symbol)[:200]],
            "impact": index.impact(symbol),
            "call_graph": index.call_graph(symbol),
        }

    @app.get("/memory")
    async def memory(q: str = "", kind: str | None = None, limit: int = Query(20, le=200)):
        s = st()
        if q:
            return dump(s.memory.recall(q, kind=kind, limit=limit))  # type: ignore[arg-type]
        return dump([m for m in s.store.memories.list(limit=500, newest_first=True) if kind is None or m.kind == kind][:limit])

    # ------------------------------------------------------------------ 2.5D studio client (static)

    ui_dir = (settings or (studio.settings if studio else None) or Settings()).ui_dir
    if ui_dir.is_dir():

        @app.get("/")
        async def index():
            return FileResponse(ui_dir / "index.html")

        app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")

    return app
