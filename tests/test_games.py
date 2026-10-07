"""One folder and repository per game, and publishing finished games into the studio repository."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from shunya.api import create_app
from shunya.core.games import name_from_request, slugify
from shunya.core.models.demo_scripts import demo_scripts
from shunya.core.models.scripted_provider import ScriptedProvider
from shunya.shared.schemas import ApprovalStatus, EventType, TaskStatus
from shunya.studio import Studio
from shunya.tools.git_tools import git

from .conftest import FakeBuildService, FakeContentService, FakePackageService, FakePlaytestService, FakeTestService, child_tasks, status_of, wait_for

HEALTH = "Create a simple Unreal health component."
HEADER = "Source/ShunyaGame/Public/Components/HealthComponent.h"


def test_game_names_from_requests():
    assert name_from_request("Build Orb Runner: a small 3D arena game where the player collects orbs") == "Orb Runner"
    assert name_from_request("Create a simple Unreal health component.") == "Unreal health component"
    assert name_from_request("make a game called Star Hopper with jumping") == "Star Hopper"
    assert name_from_request("!!!") == "Game"
    assert slugify("Orb Runner") == "orb-runner" and slugify("  Star--Hopper 2!  ") == "star-hopper-2" and slugify("?") == "game"
    assert len(slugify("x" * 200)) <= 39


async def _finish(studio, feature):
    approval = await wait_for(lambda: next(iter(studio.store.approvals.list(status=str(ApprovalStatus.PENDING))), None))
    await studio.approvals.decide(approval.id, granted=True, decided_by="studio_owner")
    await wait_for(lambda: status_of(studio, feature.id) == TaskStatus.DONE)


async def test_each_game_gets_its_own_folder_and_history(make_studio):
    studio = await make_studio(inject=False)
    first = await studio.orchestrator.submit_feature(HEALTH, game="Alpha Quest")
    await _finish(studio, first)
    second = await studio.orchestrator.submit_feature(HEALTH, game="Beta Racer")
    await _finish(studio, second)

    games = {g.id: g for g in studio.games.all()}
    assert set(games) == {"alpha-quest", "beta-racer"}
    alpha, beta = Path(games["alpha-quest"].repo_path), Path(games["beta-racer"].repo_path)
    assert alpha == studio.settings.games_dir / "alpha-quest" and beta == studio.settings.games_dir / "beta-racer"
    assert (alpha / ".git").is_dir() and (beta / ".git").is_dir() and (alpha / "ShunyaGame.uproject").is_file()
    assert first.game_id == "alpha-quest" and all(t.game_id == "alpha-quest" for t in child_tasks(studio, first.id))
    for repo, feature in ((alpha, first), (beta, second)):
        log = (await git(repo, "log", "--oneline", "develop")).out
        task = child_tasks(studio, feature.id)[0]
        assert f"Merge agent/{task.id}" in log and (await git(repo, "show", f"develop:{HEADER}", check=False)).code == 0
    # histories are separate: one game's task never appears in the other's repository
    assert child_tasks(studio, second.id)[0].id not in (await git(alpha, "log", "--oneline", "--all")).out
    created = [e.payload["game_id"] for e in studio.store.events.since(0, limit=5000) if e.type == EventType.GAME_CREATED]
    assert created == ["alpha-quest", "beta-racer"]

    # naming an existing game continues it in the same folder instead of creating another
    third = await studio.orchestrator.submit_feature(HEALTH, game="alpha quest")
    assert third.game_id == "alpha-quest" and len(studio.games.all()) == 2
    await studio.orchestrator.cancel(third.id)
    await studio.stop()


async def test_finished_game_is_committed_into_the_studio_repository(make_studio, settings, tmp_path):
    studio_repo = tmp_path / "studio_repo"
    studio_repo.mkdir()
    await git(studio_repo, "init", "-b", "main")
    (studio_repo / "README.md").write_text("studio\n", encoding="utf-8")
    (studio_repo / "unrelated.txt").write_text("v1\n", encoding="utf-8")
    await git(studio_repo, "add", "-A")
    await git(studio_repo, "commit", "-m", "initial")
    (studio_repo / "unrelated.txt").write_text("uncommitted local edit\n", encoding="utf-8")  # must not be swept into the game commit
    settings.publish_games, settings.publish_repo = True, studio_repo

    studio = await make_studio(inject=False)
    feature = await studio.orchestrator.submit_feature(HEALTH, game="Alpha Quest")
    await _finish(studio, feature)

    result = studio.store.tasks.get(feature.id).result["publish"]
    assert result["published"] is True and result["pushed"] is False
    folder = studio_repo / "games" / "alpha-quest"
    assert (folder / HEADER).is_file() and (folder / "ShunyaGame.uproject").is_file() and "Alpha Quest" in (folder / "GAME.md").read_text(encoding="utf-8")
    assert not (folder / "Binaries").exists() and not (folder / ".git").exists()  # a snapshot of sources, not a nested repository
    committed = (await git(studio_repo, "show", "--name-only", "--pretty=format:%s", "HEAD")).out.splitlines()
    assert committed[0].startswith("games/alpha-quest: ") and feature.id in committed[0]
    assert all(line.startswith("games/alpha-quest/") for line in committed[1:] if line)
    assert " M unrelated.txt" in (await git(studio_repo, "status", "--porcelain")).out  # the owner's other work is untouched
    game = studio.games.get("alpha-quest")
    assert game.published_commit == result["commit"] and game.published_source == result["source_commit"]
    assert any(e.type == EventType.GAME_PUBLISHED for e in studio.store.events.since(0, limit=5000))
    again = await studio.publisher.publish("alpha-quest", "again")
    assert again["published"] is False and "no changes" in again["reason"]
    await studio.stop()


def test_games_api_and_adopting_folders(settings):
    studio = Studio(settings, provider=ScriptedProvider(demo_scripts(inject_compile_error=False)), build=FakeBuildService(), tests=FakeTestService(),
                    content=FakeContentService(), playtest=FakePlaytestService(), packager=FakePackageService())
    with TestClient(create_app(studio)) as client:
        assert client.get("/games").json() == []
        assert client.get("/knowledge/search", params={"q": "health"}).status_code == 404  # no game yet
        feature = client.post("/tasks", json={"request": HEALTH, "game": "Delta Dash"}).json()
        assert feature["game_id"] == "delta-dash"
        listing = client.get("/games").json()
        assert [g["id"] for g in listing] == ["delta-dash"] and listing[0]["repo_path"].endswith("delta-dash")
        assert client.get("/studio/state").json()["games"][0]["id"] == "delta-dash"
        assert client.post("/games/nope/publish").status_code == 404
        assert client.post(f"/tasks/{feature['id']}/cancel").status_code == 200
    # a new studio process on the same folders but an empty database finds the game again
    (settings.data_dir / "shunya.db").unlink()
    reborn = Studio(settings, provider=ScriptedProvider(demo_scripts()), build=FakeBuildService(), tests=FakeTestService())
    assert [g.id for g in reborn.games.adopt_existing()] == ["delta-dash"]
    reborn.store.close()
