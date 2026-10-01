"""REST + WebSocket API (spec 26) and knowledge retrieval (spec 22, 23)."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from shunya.api import create_app
from shunya.core.models.demo_scripts import HEADER, SOURCE, TESTS, demo_scripts
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.knowledge import CppIndex, HybridRetriever
from shunya.studio import Studio

from .conftest import FakeBuildService, FakeTestService

TEMPLATE = Path(__file__).resolve().parent.parent / "unreal" / "ShunyaGame"


def _poll(fn, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def test_api_end_to_end(settings):
    studio = Studio(settings, provider=ScriptedProvider(demo_scripts(inject_compile_error=True)), build=FakeBuildService(), tests=FakeTestService())
    with TestClient(create_app(studio)) as client:
        state = client.get("/studio/state").json()
        assert state["studio"] == "SHUNYA STUDIOS" and state["stats"]["agents"] == 7
        offline = [a for a in state["agents"] if not a["enabled"]]
        assert offline and all(a["state"] == "OFFLINE" for a in offline)  # defined but unimplemented roles are empty desks

        assert client.post("/tasks", json={"request": "x"}).status_code == 422
        with client.websocket_connect("/ws/studio?since=0") as ws:
            assert ws.receive_json()["kind"] == "hello"
            feature = client.post("/tasks", json={"request": "Create a simple Unreal health component."}).json()
            assert feature["id"].startswith("FEAT-") and feature["status"] == "BACKLOG"
            seqs, types = [], set()
            while "APPROVAL_REQUIRED" not in types:
                msg = ws.receive_json()
                seqs.append(msg["event"]["seq"])
                types.add(msg["event"]["type"])
            assert seqs == sorted(set(seqs)), "events arrive in order, exactly once"
            assert {"AGENT_STATUS_CHANGED", "AGENT_TOOL_CALLED", "BUILD_FAILED", "BUILD_PASSED", "TEST_PASSED", "MEETING_STARTED"} <= types

        approvals = client.get("/approvals", params={"status": "PENDING"}).json()
        assert len(approvals) == 1
        detail = client.get(f"/approvals/{approvals[0]['id']}").json()
        assert "UHealthComponent" in detail["diff"] and detail["risk_level"] == "LOW"

        task_id = approvals[0]["task_id"]
        task = client.get(f"/tasks/{task_id}").json()
        assert task["status"] == "AWAITING_APPROVAL" and len(task["builds"]) == 3 and task["runs"] and task["artifacts"]
        assert "UHealthComponent" in client.get(f"/tasks/{task_id}/diff").text

        owner = task["owner"]
        agent = client.get(f"/agents/{owner}").json()
        assert agent["state"] == "WAITING_APPROVAL" and agent["activity"] and agent["profile"]["permissions"]["merge"] == "NO"
        assert "Recent activity" in client.get(f"/agents/{owner}/report").json()["report"]
        assert client.post(f"/agents/{owner}/pause").json()["paused"] is True
        assert client.post(f"/agents/{owner}/resume").json()["paused"] is False

        trace = client.get(f"/traces/{task['trace_id']}").json()
        assert {r["agent_id"] for r in trace["runs"]} >= {"studio_director_01", "producer_01", owner, "technical_director_01", "qa_functional_01"}
        assert any(r["tool_calls"] for r in trace["runs"])
        assert client.get("/costs").json()["llm_calls"] > 10
        assert client.get("/builds").json()[0]["status"] == "PASSED"
        assert client.get("/unreal/status").json()["editor_bridge"]["connected"] is False
        assert client.get("/events", params={"since": 0, "limit": 5}).json()[0]["seq"] == 1

        assert client.post(f"/approvals/{approvals[0]['id']}/approve", json={"comment": "ship it"}).json()["status"] == "GRANTED"
        assert client.post(f"/approvals/{approvals[0]['id']}/approve").status_code == 409
        _poll(lambda: client.get(f"/tasks/{feature['id']}").json()["status"] == "DONE")
        assert client.get("/studio/state").json()["epic"]["progress"] == 100
        assert client.post(f"/tasks/{task_id}/retry").status_code == 409
        assert client.get("/tasks/NOPE-1").status_code == 404

        # after the merge the knowledge index sees the new class on develop
        hits = client.get("/knowledge/search", params={"q": "UHealthComponent ApplyDamage"}).json()["results"]
        assert any("HealthComponent" in h["source"] for h in hits)
        graph = client.get("/knowledge/graph", params={"symbol": "UHealthComponent"}).json()
        assert any(e["type"] == "INHERITS" and e["dst"] == "UActorComponent" for e in graph["edges"])


def _project_with_health(tmp_path: Path) -> Path:
    import shutil

    root = tmp_path / "proj"
    shutil.copytree(TEMPLATE, root, ignore=shutil.ignore_patterns("Binaries", "Intermediate", "Saved"))
    for rel, text in (
        ("Source/ShunyaGame/Public/Components/HealthComponent.h", HEADER),
        ("Source/ShunyaGame/Private/Components/HealthComponent.cpp", SOURCE.replace("__MAX__", "MaxHealth")),
        ("Source/ShunyaGame/Private/Tests/HealthComponentTests.cpp", TESTS),
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_cpp_index_and_dependency_graph(tmp_path):
    index = CppIndex(_project_with_health(tmp_path)).build()
    cls = index.find_symbol("UHealthComponent")[0]
    assert cls.kind == "class" and cls.unreal == "UCLASS" and cls.bases == ["UActorComponent"]
    assert cls.file.endswith("Public/Components/HealthComponent.h")
    methods = {s.qualified for s in index.symbols if s.kind == "method"}
    assert {"UHealthComponent::ApplyDamage", "UHealthComponent::Heal", "UHealthComponent::CanMutate"} <= methods
    edges = {(e.src, e.type, e.dst) for e in index.edges}
    assert ("UHealthComponent", "INHERITS", "UActorComponent") in edges
    assert ("ShunyaGame", "DEPENDS_ON", "Engine") in edges and ("ShunyaAgentBridgeEditor", "DEPENDS_ON", "HTTPServer") in edges
    assert ("Source/ShunyaGame/Private/Components/HealthComponent.cpp", "INCLUDES", "Components/HealthComponent.h") in edges
    assert "CanMutate" in index.call_graph("UHealthComponent::ApplyDamage")["calls"]
    assert "UHealthComponent::Heal" in index.call_graph("CanMutate")["called_by"]
    refs = index.find_references("UHealthComponent")
    assert {Path(f).name for f, _, _ in refs} >= {"HealthComponent.h", "HealthComponent.cpp", "HealthComponentTests.cpp"}
    impact = index.impact("UHealthComponent")
    assert any("HealthComponentTests.cpp" in item for items in impact.values() for item in items)


def test_hybrid_retrieval_returns_minimal_relevant_context(tmp_path):
    retriever = HybridRetriever().ingest(_project_with_health(tmp_path))
    by_symbol = retriever.search("How does UHealthComponent apply damage?", limit=4)
    assert by_symbol[0]["source"].endswith(("HealthComponent.h", "HealthComponent.cpp")) and "symbol" in by_symbol[0]["matched_by"]
    docs = retriever.search("multiplayer replication standards for components", limit=4)
    assert any(r["kind"] == "doc" and "CodingStandards" in r["source"] for r in docs)
    words = retriever.search("health component death event", limit=5)
    assert any("HealthComponent" in r["source"] for r in words)
    small = retriever.search("health component", limit=20, max_chars=1500)
    assert sum(len(r["content"]) for r in small) <= 1500 + max(len(r["content"]) for r in small)
    assert len(retriever.search("health", limit=2)) <= 2
