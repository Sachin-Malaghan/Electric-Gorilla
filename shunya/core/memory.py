"""Memory (spec 21). Different kinds of memory live in different places:

- working memory      -> the run's message list (agent_runtime)
- conversation memory -> the task's handoff messages / feedback (store.messages, Task.feedback)
- project memory      -> MemoryKind.PROJECT records (standards, decisions, ADRs)
- semantic memory     -> knowledge.HybridRetriever
- episodic memory     -> MemoryKind.EPISODIC records, one per finished run
- operational memory  -> MemoryKind.OPERATIONAL records (build / test failures) + builds/tests tables
- structured memory   -> the SQL store itself
"""

from __future__ import annotations

from shunya.core.interfaces import IMemoryProvider
from shunya.core.persistence import Store
from shunya.knowledge.retriever import tokenize
from shunya.shared.schemas import MemoryKind, MemoryRecord


class MemoryService(IMemoryProvider):
    def __init__(self, store: Store):
        self.store = store

    def remember(self, record: MemoryRecord) -> MemoryRecord:
        return self.store.memories.put(record)

    def recall(self, query: str, *, kind: MemoryKind | None = None, agent_id: str | None = None, limit: int = 5) -> list[MemoryRecord]:
        records = self.store.memories.list(limit=2000, newest_first=True)
        q = set(tokenize(query))
        scored: list[tuple[float, MemoryRecord]] = []
        for i, r in enumerate(records):
            if kind is not None and r.kind != kind:
                continue
            if agent_id is not None and r.agent_id not in (None, agent_id):
                continue
            overlap = len(q & set(tokenize(f"{r.title} {r.content} {' '.join(r.tags)}")))
            if overlap == 0 and kind != MemoryKind.PROJECT:
                continue
            scored.append((overlap - i * 0.001, r))  # small recency tie-break
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def render(self, records: list[MemoryRecord], max_chars: int = 3000) -> str:
        out, used = [], 0
        for r in records:
            block = f"- [{r.kind}] {r.title}: {r.content}"
            if used + len(block) > max_chars:
                break
            out.append(block)
            used += len(block)
        return "\n".join(out)
