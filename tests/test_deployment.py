"""Deployment hardening: API token, health, feature limit, process cleanup, doctor, backup, logging."""

from __future__ import annotations

import subprocess
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shunya import cli
from shunya.api import create_app
from shunya.core import processes
from shunya.core.models.demo_scripts import demo_scripts
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.doctor import FAIL, run_checks
from shunya.logging_setup import configure
from shunya.studio import Studio

from .conftest import FakeBuildService, FakeContentService, FakePackageService, FakePlaytestService, FakeTestService


def _studio(settings) -> Studio:
    return Studio(settings, provider=ScriptedProvider(demo_scripts(inject_compile_error=False)), build=FakeBuildService(), tests=FakeTestService(),
                  content=FakeContentService(), playtest=FakePlaytestService(), packager=FakePackageService())


def test_api_requires_the_token_when_one_is_set(settings):
    settings.api_token = "s3cret-token"
    with TestClient(create_app(_studio(settings))) as client:
        health = client.get("/health")  # liveness stays open, and reveals nothing sensitive
        assert health.status_code == 200 and health.json()["auth_required"] is True and "data_dir" not in health.json()
        assert client.get("/").status_code == 200  # the page itself loads so it can ask for the token
        for path in ("/studio/state", "/tasks", "/agents", "/events", "/system", "/approvals", "/costs"):
            assert client.get(path).status_code == 401, path
        assert client.post("/tasks", json={"request": "Create a simple Unreal health component."}).status_code == 401
        assert client.post("/settings/approval-policy", json={"max_risk": "LOW"}).status_code == 401
        assert client.get("/studio/state", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/studio/state", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
        assert client.get("/studio/state", headers={"X-Shunya-Token": "s3cret-token"}).status_code == 200
        assert client.get("/studio/state", cookies={"shunya_token": "s3cret-token"}).status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("/ws/studio"):
                pass
        assert closed.value.code == 4401
        with client.websocket_connect("/ws/studio?token=s3cret-token") as ws:
            assert ws.receive_json()["kind"] == "hello"


def test_open_by_default_on_loopback_and_feature_limit(settings):
    settings.max_active_features = 1
    with TestClient(create_app(_studio(settings))) as client:
        assert client.get("/health").json()["auth_required"] is False
        system = client.get("/system").json()
        assert system["limits"]["max_active_features"] == 1 and system["child_processes"] == []
        first = client.post("/tasks", json={"request": "Create a simple Unreal health component."})
        assert first.status_code == 201
        second = client.post("/tasks", json={"request": "Create a simple Unreal health component."})
        assert second.status_code == 429 and "already in flight" in second.json()["detail"]
        assert client.post(f"/tasks/{first.json()['id']}/cancel").status_code == 200
        deadline = time.time() + 30  # cancellation lands at the pipeline's next checkpoint
        while client.get(f"/tasks/{first.json()['id']}").json()["status"] != "CANCELLED":
            assert time.time() < deadline
            time.sleep(0.1)
        assert client.post("/tasks", json={"request": "Create a simple Unreal health component."}).status_code == 201


def test_serve_refuses_a_public_address_without_a_token(monkeypatch, capsys):
    monkeypatch.delenv("SHUNYA_API_TOKEN", raising=False)
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8499"]) == 2
    assert "Refusing to listen on 0.0.0.0 without an access token" in capsys.readouterr().out


def test_child_process_trees_are_killed():
    # a parent that starts a child and both sleep: killing the tree must take the child too
    code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); print(p.pid, flush=True); time.sleep(120)"
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    processes.register(parent.pid)
    assert parent.pid in processes.active()
    assert processes.kill_all() >= 1
    parent.wait(timeout=20)
    assert processes.active() == []
    listing = subprocess.run(["tasklist", "/FI", f"PID eq {child_pid}"], capture_output=True, text=True).stdout if sys.platform == "win32" else ""
    assert str(child_pid) not in listing


def test_doctor_reports_problems(settings):
    checks = {c.name: c for c in run_checks(settings)}
    assert checks["Python"].status == "ok" and checks["Git"].status == "ok" and checks["Database"].status == "ok"
    assert checks["Unreal Engine"].status == "warn"  # tests run without an engine
    assert checks["API access"].status == "warn"
    settings.host = "0.0.0.0"
    assert {c.name: c for c in run_checks(settings)}["API access"].status == FAIL
    settings.api_token = "x" * 24
    assert {c.name: c for c in run_checks(settings)}["API access"].status == "ok"
    settings.workspace_dir = settings.workspace_dir / ("deep" * 30)
    assert {c.name: c for c in run_checks(settings)}["Workspace path length"].status == FAIL


def test_backup_archives_database_and_artifacts(settings, monkeypatch, tmp_path):
    studio = _studio(settings)
    studio.artifacts.put(type="BuildLog", title="log", creator="t", content="hello artifact")  # type: ignore[arg-type]
    studio.store.close()
    monkeypatch.setattr(cli, "load_settings", lambda **_: settings)
    target = tmp_path / "out" / "backup.zip"
    assert cli.main(["backup", "--output", str(target)]) == 0
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        assert "shunya.db" in names and any(n.startswith("artifacts/") for n in names)
        assert z.read("shunya.db")[:15] == b"SQLite format 3"


def test_logging_writes_a_rotating_file(tmp_path):
    import logging

    path = configure(tmp_path / "logs", level="INFO")
    logging.getLogger("shunya.test").info("studio started %s", 42)
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "studio started 42" in path.read_text(encoding="utf-8")
    logging.getLogger().handlers.clear()
