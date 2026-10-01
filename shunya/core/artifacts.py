"""Versioned artifact store (spec 36). Content on disk, metadata in the structured store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shunya.core.interfaces import IArtifactStore
from shunya.core.persistence import Store
from shunya.shared.schemas import Artifact, ArtifactType

_EXT = {"text/plain": ".txt", "text/markdown": ".md", "application/json": ".json", "text/x-diff": ".diff", "image/png": ".png"}


class FileArtifactStore(IArtifactStore):
    def __init__(self, root: Path, store: Store):
        self.root = root
        self.store = store
        root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        type: ArtifactType,
        title: str,
        creator: str,
        content: str | bytes,
        task_id: str | None = None,
        content_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
        status: str = "FINAL",
    ) -> Artifact:
        previous = [a for a in self.store.artifacts.list(task_id=task_id) if a.type == type and a.title == title] if task_id else []
        art = Artifact(
            type=type, title=title, creator=creator, task_id=task_id, version=len(previous) + 1,
            status=status, content_type=content_type, metadata=metadata or {},
        )
        path = self.root / f"{art.id}{_EXT.get(content_type, '.bin')}"
        data = content.encode("utf-8") if isinstance(content, str) else content
        path.write_bytes(data)
        art.storage_location = str(path)
        art.metadata.setdefault("bytes", len(data))
        self.store.artifacts.put(art)
        return art

    def get(self, artifact_id: str) -> Artifact | None:
        return self.store.artifacts.get(artifact_id)

    def read(self, artifact_id: str) -> bytes:
        art = self.get(artifact_id)
        if art is None:
            raise KeyError(artifact_id)
        path = Path(art.storage_location).resolve()
        if self.root.resolve() not in path.parents:
            raise PermissionError("artifact path outside the artifact store")
        return path.read_bytes()

    def read_text(self, artifact_id: str) -> str:
        return self.read(artifact_id).decode("utf-8", "replace")
