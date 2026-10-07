"""One folder and one git repository per game.

`workspace/games/<slug>/` is created from the template the first time a game is named in a
request. Each is an independent repository (`main`, `develop`, `agent/<TASK>` branches), so
several games can be developed side by side and each has its own history. The folders are
the source of truth: any repository found there is adopted on start.

Publishing copies a finished game's `develop` snapshot into `games/<slug>/` of the studio
repository and commits it there (only that folder), so what the studio built is versioned
alongside the studio itself.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import zipfile
from pathlib import Path

from shunya.config import Settings
from shunya.core.persistence import Store
from shunya.shared.schemas import Game, MemoryKind, MemoryRecord, utcnow
from shunya.tools.git_tools import DEVELOP, GitError, GitService, git

log = logging.getLogger(__name__)
_LEAD_IN = {"build", "create", "make", "develop", "add", "implement", "write", "design", "a", "an", "the", "new", "simple", "small", "tiny", "me", "us", "please", "game", "called", "named"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:39].strip("-")
    return slug if len(slug) >= 2 else "game"


def name_from_request(text: str) -> str:
    """A short game name from a request: 'Build Orb Runner: a small arena game' -> 'Orb Runner'."""
    head = re.split(r"[:.\n,;-]", text.strip(), maxsplit=1)[0]
    words = [w for w in re.findall(r"[A-Za-z0-9]+", head)]
    while words and words[0].lower() in _LEAD_IN:
        words.pop(0)
    picked: list[str] = []
    for w in words:
        if w.lower() in ("where", "that", "with", "in", "for", "to", "which", "game"):
            break
        picked.append(w)
        if len(picked) == 3:
            break
    return " ".join(picked) or "Game"


class GameRegistry:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self._git: dict[str, GitService] = {}

    def all(self) -> list[Game]:
        return self.store.games.list(limit=1000)

    def get(self, game_id: str) -> Game | None:
        return self.store.games.get(game_id) if game_id else None

    def repo(self, game_id: str) -> Path:
        game = self.get(game_id)
        if game is None:
            raise KeyError(f"unknown game '{game_id}'")
        return Path(game.repo_path)

    def git(self, game_id: str) -> GitService:
        if game_id not in self._git:
            self._git[game_id] = GitService(self.repo(game_id), self.settings.worktrees_dir)
        return self._git[game_id]

    def for_task(self, task_id: str | None) -> Game | None:
        task = self.store.tasks.get(task_id) if task_id else None
        return self.get(task.game_id) if task else None

    def adopt_existing(self) -> list[Game]:
        """Register game folders that exist on disk but not in the database (restore, manual copy)."""
        adopted = []
        root = self.settings.games_dir
        for folder in sorted(root.iterdir()) if root.is_dir() else []:
            if (folder / ".git").exists() and SLUG.match(folder.name) and self.get(folder.name) is None:
                game = Game(id=folder.name, name=folder.name.replace("-", " ").title(), repo_path=str(folder))
                self.store.games.put(game)
                adopted.append(game)
        return adopted

    async def ensure(self, name: str) -> Game:
        """The game with this name, created from the template if it does not exist yet."""
        game_id = slugify(name)
        existing = self.get(game_id)
        if existing is not None and (Path(existing.repo_path) / ".git").exists():
            return existing
        repo = self.settings.games_dir / game_id
        await GitService(repo, self.settings.worktrees_dir).ensure_repo(self.settings.game_template)
        game = Game(id=game_id, name=name.strip()[:60] or game_id, repo_path=str(repo))
        self.store.games.put(game)
        self._git.pop(game_id, None)
        self._seed_memory(game)
        log.info("created game '%s' at %s", game_id, repo)
        return game

    def _seed_memory(self, game: Game) -> None:
        """Project memory: the standards and decisions agents retrieve before acting (spec 37)."""
        existing = {m.title for m in self.store.memories.list(limit=5000) if m.kind == MemoryKind.PROJECT}
        docs = Path(game.repo_path) / "Docs"
        for path in sorted([*docs.glob("adr/*.md"), *docs.glob("CodingStandards.md")]):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
            if title not in existing:
                self.store.memories.put(MemoryRecord(kind=MemoryKind.PROJECT, title=title, content=text[:1500], tags=["adr", path.stem]))


class GamePublisher:
    """Commits a game's develop snapshot into `games/<slug>/` of the studio repository."""

    def __init__(self, settings: Settings, registry: GameRegistry):
        self.settings = settings
        self.registry = registry

    async def publish(self, game_id: str, message: str) -> dict:
        game = self.registry.get(game_id)
        if game is None:
            raise KeyError(f"unknown game '{game_id}'")
        target_repo = self.settings.publish_repo
        if target_repo is None or not (target_repo / ".git").exists():
            return {"published": False, "reason": f"{target_repo} is not a git repository"}
        source = Path(game.repo_path)
        head = (await git(source, "rev-parse", DEVELOP)).out.strip()
        archive = source / "Saved" / "Shunya" / "publish.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        await git(source, "archive", "--format=zip", "-o", str(archive), DEVELOP)
        dest = target_repo / "games" / game.id
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(archive.read_bytes())) as z:
            z.extractall(dest)
        archive.unlink(missing_ok=True)
        (dest / "GAME.md").write_text(
            f"# {game.name}\n\nBuilt by Shunya Studio AI. This folder is a snapshot of the game repository's `develop` branch "
            f"at commit `{head}`, published {utcnow():%Y-%m-%d %H:%M} UTC.\n\n"
            "The full per-task history lives in the studio's working repository for this game; binaries and packaged builds are not stored here.\n",
            encoding="utf-8", newline="\n",
        )
        rel = f"games/{game.id}"
        await git(target_repo, "add", "-A", "--", rel)
        if (await git(target_repo, "diff", "--cached", "--quiet", "--", rel, check=False)).code == 0:
            return {"published": False, "reason": "no changes since the last publish", "path": str(dest), "source_commit": head}
        # commit only this game's folder, whatever else is staged or modified in the studio repository
        await git(target_repo, "commit", "-m", f"{rel}: {message}", "--", rel)
        commit = (await git(target_repo, "rev-parse", "HEAD")).out.strip()
        pushed = False
        if self.settings.publish_push:
            try:
                await git(target_repo, "push", "origin", "HEAD", timeout=300)
                pushed = True
            except GitError as e:
                log.warning("publish push failed: %s", e)
        game.published_commit, game.published_source, game.published_at = commit, head, utcnow()
        self.registry.store.games.put(game)
        return {"published": True, "commit": commit, "pushed": pushed, "path": str(dest), "source_commit": head}
