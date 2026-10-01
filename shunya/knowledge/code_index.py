"""C++ / Unreal symbol index and dependency graph (spec 22, 23).

V1 is a fast regex-based indexer tuned to Unreal's conventions (UCLASS / UPROPERTY /
Module.Build.cs). It is deliberately behind a small API (find_symbol, references, graph)
so it can be replaced by a libclang or tree-sitter backend without touching the tools.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs"}
CODE_EXT = {".h", ".hpp", ".cpp", ".inl", ".cs"}

_CLASS = re.compile(
    r"^[ \t]*(class|struct)\s+(?:[A-Z0-9_]+_API\s+)?([A-Za-z_]\w*)\s*(?:final\s*)?(?::\s*([^{;]+?))?\s*\{", re.M
)
_ENUM = re.compile(r"^[ \t]*enum\s+(?:class\s+)?([A-Za-z_]\w*)", re.M)
# definitions start at column 0; an indented `Foo::Bar(` is a call
_METHOD_DEF = re.compile(r"^(?:[\w:<>\*&,]+[ \t]+)*?([A-Za-z_]\w*)::(~?[A-Za-z_]\w*)\s*\(", re.M)
_FUNC_DECL = re.compile(
    r"^[ \t]+(?:(?:virtual|static|explicit|inline|FORCEINLINE|constexpr)\s+)*(?:[\w:<>\*&,]+[ \t]+)+\**&?([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:override\s*)?(?:final\s*)?[;{]",
    re.M,
)
_INCLUDE = re.compile(r'^[ \t]*#include\s+"([^"]+)"', re.M)
_UPROPERTY_MEMBER = re.compile(r"UPROPERTY\s*\([^)]*\)\s*\n?[ \t]*([\w:<>\*& ,]+?)[ \t]+\**([A-Za-z_]\w*)\s*(?:=[^;]*)?;", re.M)
_MODULE_DEP = re.compile(r"(?:Public|Private)DependencyModuleNames\.AddRange\s*\(\s*new\s+string\[\]\s*\{([^}]*)\}", re.S)
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_UE_MACRO = re.compile(r"^[ \t]*(UCLASS|USTRUCT|UENUM|UINTERFACE)\s*\(", re.M)
_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "catch", "check", "ensure", "TEXT", "static_cast", "Cast", "defined"}


@dataclass
class Symbol:
    name: str
    kind: str  # class | struct | enum | method | function | module
    file: str
    line: int
    owner: str | None = None  # class for methods
    bases: list[str] = field(default_factory=list)
    unreal: str | None = None  # UCLASS / USTRUCT / ...

    @property
    def qualified(self) -> str:
        return f"{self.owner}::{self.name}" if self.owner else self.name


@dataclass
class Edge:
    src: str
    type: str  # CALLS INHERITS OWNS INCLUDES REFERENCES DEPENDS_ON IMPLEMENTS
    dst: str


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


class CppIndex:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.files: dict[str, str] = {}  # rel path -> text
        self._by_name: dict[str, list[Symbol]] = {}

    # ------------------------------------------------------------------ build

    def source_files(self) -> list[Path]:
        out: list[Path] = []
        for top in ("Source", "Plugins"):
            base = self.root / top
            if not base.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                out += [Path(dirpath) / f for f in filenames if os.path.splitext(f)[1].lower() in CODE_EXT]
        return sorted(out)

    def build(self) -> "CppIndex":
        self.symbols.clear()
        self.edges.clear()
        self.files.clear()
        for path in self.source_files():
            rel = path.relative_to(self.root).as_posix()
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.files[rel] = raw
            text = _strip_comments(raw)
            if rel.endswith(".Build.cs"):
                self._index_module(rel, text)
                continue
            if rel.endswith(".cs"):
                continue
            self._index_cpp(rel, text)
        self._by_name = {}
        for s in self.symbols:
            self._by_name.setdefault(s.name, []).append(s)
        self._index_calls()
        return self

    def _index_module(self, rel: str, text: str) -> None:
        module = Path(rel).name.removesuffix(".Build.cs")
        self.symbols.append(Symbol(module, "module", rel, 1))
        for m in _MODULE_DEP.finditer(text):
            for dep in re.findall(r'"(\w+)"', m.group(1)):
                self.edges.append(Edge(module, "DEPENDS_ON", dep))

    def _index_cpp(self, rel: str, text: str) -> None:
        macro_lines = {_line_of(text, m.start()): m.group(1) for m in _UE_MACRO.finditer(text)}
        for inc in _INCLUDE.finditer(text):
            self.edges.append(Edge(rel, "INCLUDES", inc.group(1)))
        class_spans: list[tuple[int, int, str]] = []
        for m in _CLASS.finditer(text):
            name = m.group(2)
            line = _line_of(text, m.start())
            bases = []
            if m.group(3):
                bases = [re.sub(r"\b(public|protected|private|virtual)\b", "", b).strip() for b in m.group(3).split(",")]
                bases = [b for b in bases if b]
            unreal = next((macro_lines[l] for l in (line - 1, line - 2, line - 3) if l in macro_lines), None)
            self.symbols.append(Symbol(name, m.group(1), rel, line, bases=bases, unreal=unreal))
            for b in bases:
                self.edges.append(Edge(name, "IMPLEMENTS" if b.startswith("I") and len(b) > 1 and b[1].isupper() else "INHERITS", b))
            class_spans.append((m.end(), self._block_end(text, m.end() - 1), name))
        for m in _ENUM.finditer(text):
            self.symbols.append(Symbol(m.group(1), "enum", rel, _line_of(text, m.start())))
        for start, end, cls in class_spans:
            body = text[start:end]
            for m in _FUNC_DECL.finditer(body):
                if m.group(1) not in _KEYWORDS and m.group(1) != cls:
                    self.symbols.append(Symbol(m.group(1), "method", rel, _line_of(text, start + m.start(1)), owner=cls))
            for m in _UPROPERTY_MEMBER.finditer(body):
                t = re.search(r"\b([AU][A-Z]\w+)\s*>?\s*\*?\s*$", m.group(1).strip())
                if t:
                    self.edges.append(Edge(cls, "OWNS", t.group(1)))
        if rel.endswith(".cpp"):
            for m in _METHOD_DEF.finditer(text):
                owner, name = m.group(1), m.group(2)
                if owner in _KEYWORDS or name.lstrip("~") == owner:  # constructors/destructors are not separate symbols
                    continue
                self.symbols.append(Symbol(name, "method", rel, _line_of(text, m.start(1)), owner=owner))

    @staticmethod
    def _block_end(text: str, open_brace: int) -> int:
        depth = 0
        for i in range(open_brace, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        return len(text)

    def _index_calls(self) -> None:
        known = {s.name for s in self.symbols if s.kind in ("method", "function")}
        for rel, raw in self.files.items():
            if not rel.endswith(".cpp"):
                continue
            text = _strip_comments(raw)
            for m in _METHOD_DEF.finditer(text):
                brace = text.find("{", m.end())
                semi = text.find(";", m.end())
                if brace == -1 or (semi != -1 and semi < brace):
                    continue
                body = text[brace : self._block_end(text, brace)]
                caller = f"{m.group(1)}::{m.group(2)}"
                seen: set[str] = set()
                for c in _CALL.finditer(body):
                    callee = c.group(1)
                    if callee in known and callee != m.group(2) and callee not in seen:
                        seen.add(callee)
                        self.edges.append(Edge(caller, "CALLS", callee))

    # ------------------------------------------------------------------ queries

    def find_symbol(self, name: str) -> list[Symbol]:
        exact = self._by_name.get(name.split("::")[-1], [])
        if exact:
            return sorted(exact, key=lambda s: (s.kind == "method", not s.file.endswith(".h")))
        low = name.lower()
        return [s for s in self.symbols if low in s.name.lower()][:40]

    def find_references(self, name: str, limit: int = 120) -> list[tuple[str, int, str]]:
        rx = re.compile(rf"\b{re.escape(name)}\b")
        hits: list[tuple[str, int, str]] = []
        for rel, text in self.files.items():
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append((rel, i, line.strip()[:200]))
                    if len(hits) >= limit:
                        return hits
        return hits

    def edges_of(self, node: str) -> list[Edge]:
        short = node.split("::")[-1]
        base = Path(node).name
        return [e for e in self.edges if e.src in (node, short) or e.dst in (node, short, base) or e.src.startswith(f"{node}::")]

    def impact(self, name: str, depth: int = 2) -> dict[str, list[str]]:
        """What could be affected by changing `name`: dependents by relation, transitively."""
        frontier, seen = {name}, {name}
        result: dict[str, list[str]] = {}
        for _ in range(depth):
            nxt: set[str] = set()
            for e in self.edges:
                dst_names = {e.dst, Path(e.dst).name, Path(e.dst).stem}
                if frontier & dst_names and e.src not in seen:
                    result.setdefault(e.type, []).append(f"{e.src} -> {e.dst}")
                    nxt.add(e.src)
                    nxt.add(e.src.split("::")[0])
            # a header's includers are affected when a class declared in it changes
            for sym in [s for n in frontier for s in self._by_name.get(n, []) if s.kind in ("class", "struct")]:
                nxt.add(sym.file)
                nxt.add(Path(sym.file).name)
            nxt -= seen
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        declared_in = {s.file for s in self._by_name.get(name, [])}
        users = sorted({f for f, _, _ in self.find_references(name, limit=400)} - declared_in)
        if users:
            result["REFERENCES"] = [f"{f} -> {name}" for f in users]
        return result

    def call_graph(self, name: str) -> dict[str, list[str]]:
        short = name.split("::")[-1]
        return {
            "calls": sorted({e.dst for e in self.edges if e.type == "CALLS" and (e.src == name or e.src.endswith(f"::{short}"))}),
            "called_by": sorted({e.src for e in self.edges if e.type == "CALLS" and e.dst == short}),
        }

    def snippet(self, sym: Symbol, context: int = 30) -> str:
        lines = self.files.get(sym.file, "").splitlines()
        start = max(0, sym.line - 3)
        return "\n".join(lines[start : start + context])
