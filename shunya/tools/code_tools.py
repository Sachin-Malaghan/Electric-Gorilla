"""C++ understanding, knowledge search, compile and test tools (spec 16 - C++ / Build / Testing)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shunya.knowledge import HybridRetriever
from shunya.shared.schemas import AgentState, BuildStatus
from shunya.tools.base import Tool, ToolContext, ToolError, ToolResult


def _index(ctx: ToolContext):
    sb = ctx.require_sandbox()
    retriever = ctx.services.retriever_for(sb.root)
    assert retriever.index is not None
    return retriever.index


class FindSymbol(Tool):
    name = "find_symbol"
    description = "Find where a C++ class, struct, enum or method is declared/defined. Returns file:line and a snippet."
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        name: str = Field(description="Symbol name, e.g. UHealthComponent or TakeDamage")

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        index = _index(ctx)
        syms = index.find_symbol(args.name)
        if not syms:
            return ToolResult(content=f"No symbol named '{args.name}' in the project.", summary=f"find_symbol {args.name}: none")
        parts = []
        for s in syms[:12]:
            head = f"{s.kind} {s.qualified}  ({s.file}:{s.line})"
            if s.unreal:
                head += f"  [{s.unreal}]"
            if s.bases:
                head += f"  : {', '.join(s.bases)}"
            parts.append(head + ("\n" + index.snippet(s, 16) if s.kind in ("class", "struct", "enum") and len(syms) <= 3 else ""))
        return ToolResult(content="\n\n".join(parts), summary=f"Found {len(syms)} symbol(s) named {args.name}", files_read=list({s.file for s in syms[:12]}))


class FindReferences(Tool):
    name = "find_references"
    description = "List every place a symbol name is used across the project source."
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        name: str

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        hits = _index(ctx).find_references(args.name)
        body = "\n".join(f"{f}:{line}: {text}" for f, line, text in hits) or "(no references)"
        return ToolResult(content=body, summary=f"{len(hits)} reference(s) to {args.name}")


class InspectDependencies(Tool):
    name = "inspect_dependencies"
    description = (
        "Show dependency-graph edges for a class, file or module: INHERITS, OWNS, INCLUDES, "
        "DEPENDS_ON (Build.cs modules), CALLS. Use before changing something to see what it touches."
    )
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        target: str = Field(description="Class name, module name, or workspace-relative file path")

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        edges = _index(ctx).edges_of(args.target)
        body = "\n".join(f"{e.src} --{e.type}--> {e.dst}" for e in edges[:150]) or "(no edges)"
        return ToolResult(content=body, summary=f"{len(edges)} dependency edge(s) for {args.target}")


class AnalyzeImpact(Tool):
    name = "analyze_impact"
    description = "Impact analysis: which classes/files/modules depend (transitively) on a symbol and could break if it changes."
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        symbol: str
        depth: int = Field(default=2, ge=1, le=4)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        impact = _index(ctx).impact(args.symbol, args.depth)
        if not impact:
            return ToolResult(content=f"Nothing in the project depends on '{args.symbol}'.", summary=f"impact {args.symbol}: none")
        body = "\n".join(f"{kind}:\n  " + "\n  ".join(sorted(set(items))[:40]) for kind, items in impact.items())
        return ToolResult(content=body, summary=f"Impact analysis for {args.symbol}")


class AnalyzeCallGraph(Tool):
    name = "analyze_call_graph"
    description = "Approximate call graph for a method: what it calls and what calls it (project code only)."
    required_permissions = ["read_code"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        method: str = Field(description="Method name or Class::Method")

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        g = _index(ctx).call_graph(args.method)
        body = f"calls: {', '.join(g['calls']) or '-'}\ncalled_by: {', '.join(g['called_by']) or '-'}"
        return ToolResult(content=body, summary=f"Call graph for {args.method}")


class KnowledgeSearch(Tool):
    name = "knowledge_search"
    description = (
        "Search project knowledge (design docs, coding standards, ADRs, source) with hybrid "
        "semantic + symbol + graph retrieval. Returns the most relevant excerpts."
    )
    required_permissions = ["knowledge_search"]
    activity = AgentState.SEARCHING

    class Input(BaseModel):
        query: str
        limit: int = Field(default=6, ge=1, le=12)

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        results = ctx.services.retriever_for(sb.root).search(args.query, limit=args.limit, max_chars=10000)
        return ToolResult(
            content=HybridRetriever.render(results) or "(nothing relevant found)",
            summary=f"Knowledge search '{args.query[:50]}' ({len(results)} results)",
            files_read=[r["source"] for r in results if r["kind"] == "code"],
        )


class CompileProject(Tool):
    name = "compile_project"
    description = (
        "Compile the Unreal project in your task worktree (editor target). Returns PASSED, or FAILED with "
        "parsed compiler errors (file, line, code, message). Takes minutes - call it when you have a complete change."
    )
    required_permissions = ["compile"]
    activity = AgentState.COMPILING

    class Input(BaseModel):
        pass

    def describe_call(self, args: BaseModel) -> str:
        return "Running compilation"

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        rec = await ctx.services.run_build(
            project_dir=sb.root, task_id=ctx.task.id if ctx.task else None, agent_id=ctx.agent.id, trace_id=ctx.run.trace_id
        )
        data = {"build_id": rec.id, "status": rec.status, "errors": [d.model_dump() for d in rec.diagnostics]}
        if rec.status == BuildStatus.PASSED:
            return ToolResult(content=f"BUILD PASSED in {rec.duration_s}s (build {rec.id})", summary="Build passed", data=data)
        if rec.status == BuildStatus.SKIPPED:
            return ToolResult(ok=False, content=f"BUILD SKIPPED: {rec.log_tail}", summary="Build skipped (no engine)", data=data)
        lines = [f"BUILD {rec.status} (build {rec.id}) - {len(rec.diagnostics)} error(s):"]
        for d in rec.diagnostics[:30]:
            loc = f"{d.file}({d.line})" if d.line else d.file
            lines.append(f"  {loc}: {d.code} {d.message}".rstrip())
        return ToolResult(ok=False, content="\n".join(lines), summary=f"Build failed ({len(rec.diagnostics)} errors)", data=data)


class RunAutomationTests(Tool):
    name = "run_automation_tests"
    description = (
        "Run Unreal Automation Framework tests whose path starts with `filter` (e.g. ShunyaGame.Health) "
        "headless in your worktree. The project must compile first. Returns per-test PASS/FAIL with messages."
    )
    required_permissions = ["run_tests"]
    activity = AgentState.TESTING

    class Input(BaseModel):
        filter: str = Field(description="Test path prefix, e.g. ShunyaGame or ShunyaGame.Health")

    def describe_call(self, args: BaseModel) -> str:
        return f"Running tests {getattr(args, 'filter', '')}"

    async def run(self, ctx: ToolContext, args: Input) -> ToolResult:
        sb = ctx.require_sandbox()
        rec = await ctx.services.run_tests(
            project_dir=sb.root, test_filter=args.filter, task_id=ctx.task.id if ctx.task else None,
            agent_id=ctx.agent.id, trace_id=ctx.run.trace_id,
        )
        lines = [f"TESTS {rec.status} (run {rec.id}): {rec.passed} passed, {rec.failed} failed, filter={args.filter}"]
        for r in rec.results[:60]:
            lines.append(f"  [{r.result}] {r.name}" + (f" - {'; '.join(r.messages)}" if r.messages else ""))
        return ToolResult(
            ok=rec.status == "PASSED", content="\n".join(lines), summary=f"Tests {rec.status} ({rec.passed}/{rec.passed + rec.failed})",
            data={"test_run_id": rec.id, "status": rec.status, "passed": rec.passed, "failed": rec.failed},
        )


CODE_TOOLS = [FindSymbol, FindReferences, InspectDependencies, AnalyzeImpact, AnalyzeCallGraph, KnowledgeSearch, CompileProject, RunAutomationTests]

__all__ = ["CODE_TOOLS", "ToolError"]
