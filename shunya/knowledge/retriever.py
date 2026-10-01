"""Hybrid knowledge retrieval (spec 21, 22, 35): semantic + symbol + graph -> rerank -> minimal context.

Semantic search alone is not enough for a C++ codebase, so three retrievers run and their
rankings are fused (reciprocal rank fusion). The result is trimmed to a character budget:
agents get the smallest useful context, never the whole repository.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from shunya.core.interfaces import IKnowledgeRetriever
from shunya.knowledge.code_index import CODE_EXT, SKIP_DIRS, CppIndex
from shunya.shared.schemas import KnowledgeChunk

DOC_EXT = {".md", ".txt"}
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "is", "be", "it", "that", "this", "with", "on", "as", "by", "at"}


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN.findall(text):
        low = tok.lower()
        if low not in _STOP:
            out.append(low)
        parts = [p.lower() for p in _CAMEL.findall(tok)]
        if len(parts) > 1:
            out += [p for p in parts if len(p) > 1 and p not in _STOP]
    return out


class IEmbedder(ABC):
    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder(IEmbedder):
    """Deterministic, offline bag-of-words embedding (signed feature hashing).

    Good enough for V1 lexical-semantic recall and needs no model or network. Swap in a
    real embedding model behind IEmbedder (and pgvector for storage) when recall matters.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "little")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunk_text(source: str, text: str, kind: str, *, max_lines: int = 60, overlap: int = 8) -> list[KnowledgeChunk]:
    lines = text.splitlines()
    chunks: list[KnowledgeChunk] = []
    if kind == "doc":
        # split on markdown headings, then by size
        starts = [i for i, l in enumerate(lines) if l.startswith("#")] or [0]
        if starts[0] != 0:
            starts.insert(0, 0)
        bounds = list(zip(starts, starts[1:] + [len(lines)]))
    else:
        bounds = [(0, len(lines))]
    for lo, hi in bounds:
        i = lo
        while i < hi:
            j = min(hi, i + max_lines)
            body = "\n".join(lines[i:j]).strip()
            if body:
                chunks.append(KnowledgeChunk(id=f"{source}#{i + 1}", source=source, kind=kind, start_line=i + 1, content=body))
            if j >= hi:
                break
            i = j - overlap
    return chunks


class HybridRetriever(IKnowledgeRetriever):
    def __init__(self, embedder: IEmbedder | None = None):
        self.embedder = embedder or HashingEmbedder()
        self.chunks: list[KnowledgeChunk] = []
        self.index: CppIndex | None = None
        self.root: Path | None = None

    # ------------------------------------------------------------------ ingestion

    def ingest(self, root: Path, *, extra_docs: list[Path] | None = None) -> "HybridRetriever":
        self.root = root.resolve()
        self.chunks = []
        self.index = CppIndex(self.root).build()
        for rel, text in self.index.files.items():
            self._add(rel, text, "code")
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d not in ("Source", "Plugins", "Content")]
            for f in filenames:
                if os.path.splitext(f)[1].lower() in DOC_EXT:
                    p = Path(dirpath) / f
                    self._add(p.relative_to(self.root).as_posix(), p.read_text(encoding="utf-8", errors="replace"), "doc")
        for doc in extra_docs or []:
            if doc.is_file():
                self._add(f"studio:{doc.name}", doc.read_text(encoding="utf-8", errors="replace"), "doc")
        return self

    def _add(self, source: str, text: str, kind: str) -> None:
        if kind == "code" and os.path.splitext(source)[1].lower() not in CODE_EXT:
            return
        for c in chunk_text(source, text, kind):
            c.vector = self.embedder.embed(f"{source}\n{c.content}")
            self.chunks.append(c)

    # ------------------------------------------------------------------ search

    def _semantic(self, query: str, n: int) -> list[str]:
        qv = self.embedder.embed(query)
        scored = sorted(((cosine(qv, c.vector), c.id) for c in self.chunks), reverse=True)
        return [cid for score, cid in scored[:n] if score > 0.02]

    def _symbol(self, query: str, n: int) -> tuple[list[str], list[str]]:
        if not self.index:
            return [], []
        ids: list[str] = []
        names: list[str] = []
        for ident in dict.fromkeys(re.findall(r"\b[A-Za-z_]\w{2,}\b", query)):
            syms = self.index._by_name.get(ident, [])
            if not syms and any(ch.isupper() for ch in ident[1:]):
                syms = [s for s in self.index.symbols if ident.lower() == s.name.lower()]
            # plain words match class names by suffix: "health component" -> UHealthComponent
            for s in syms[:4]:
                names.append(s.name)
                cid = self._chunk_at(s.file, s.line)
                if cid:
                    ids.append(cid)
        words = [w for w in tokenize(query) if len(w) > 3]
        for s in self.index.symbols:
            if s.kind in ("class", "struct") and sum(1 for w in set(words) if w in s.name.lower()) >= 2:
                names.append(s.name)
                cid = self._chunk_at(s.file, s.line)
                if cid:
                    ids.append(cid)
        return list(dict.fromkeys(ids))[:n], list(dict.fromkeys(names))

    def _graph(self, names: list[str], n: int) -> list[str]:
        if not self.index:
            return []
        ids: list[str] = []
        for name in names:
            for e in self.index.edges_of(name)[:12]:
                other = e.dst if e.src == name or e.src.startswith(f"{name}::") else e.src
                for s in self.index._by_name.get(other.split("::")[-1], [])[:2]:
                    cid = self._chunk_at(s.file, s.line)
                    if cid:
                        ids.append(cid)
        return list(dict.fromkeys(ids))[:n]

    def _chunk_at(self, source: str, line: int) -> str | None:
        best = None
        for c in self.chunks:
            if c.source == source and c.start_line <= line:
                if best is None or c.start_line > best.start_line:
                    best = c
        return best.id if best else None

    def search(self, query: str, *, limit: int = 8, max_chars: int = 12000) -> list[dict[str, Any]]:
        semantic = self._semantic(query, 20)
        symbol, names = self._symbol(query, 10)
        graph = self._graph(names, 10)
        scores: dict[str, float] = {}
        why: dict[str, list[str]] = {}
        for label, ranking, weight in (("semantic", semantic, 1.0), ("symbol", symbol, 1.4), ("graph", graph, 0.8)):
            for rank, cid in enumerate(ranking):
                scores[cid] = scores.get(cid, 0.0) + weight / (60 + rank)
                why.setdefault(cid, []).append(label)
        by_id = {c.id: c for c in self.chunks}
        out: list[dict[str, Any]] = []
        used = 0
        for cid in sorted(scores, key=scores.get, reverse=True):  # type: ignore[arg-type]
            c = by_id[cid]
            if used + len(c.content) > max_chars and out:
                continue
            used += len(c.content)
            out.append({"source": c.source, "line": c.start_line, "kind": c.kind, "matched_by": why[cid], "score": round(scores[cid], 5), "content": c.content})
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def render(results: list[dict[str, Any]]) -> str:
        return "\n\n".join(f"--- {r['source']}:{r['line']} ({'+'.join(r['matched_by'])}) ---\n{r['content']}" for r in results)
