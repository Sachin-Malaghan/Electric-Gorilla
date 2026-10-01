# Architecture — how the spec maps to the code

The master specification is [SPEC.md](SPEC.md). This document says where each part lives, what was changed or added while building it, and why.

## The shape

```
            apps/studio-ui (browser, 2.5D office)
                     │  REST + WebSocket
┌────────────────────▼─────────────────────────────────────────────┐
│ shunya/api            FastAPI gateway                             │
│ shunya/studio.py      composition root (wires everything)         │
│ shunya/core/orchestration   Orchestrator · approvals · reports    │
│ shunya/core/task_engine     task state machine                    │
│ shunya/core/agent_runtime   bounded loop · registry · control     │
│ shunya/core/models          IModelProvider · router · pricing     │
│ shunya/core/permissions     capabilities · workspace sandbox      │
│ shunya/tools                files · git · C++ · build · test · UE │
│ shunya/knowledge            symbol index · graph · hybrid search  │
│ shunya/core/persistence     SQL store + append-only event log     │
│ shunya/core/events          in-memory / Redis bus                 │
│ shunya/bridge               Unreal Bridge client                  │
└───────────────┬───────────────────────────────┬──────────────────┘
                │ UnrealBuildTool / Editor-Cmd  │ HTTP (localhost)
        workspace/wt/<TASK>  (git worktree)     ShunyaAgentBridge plugin
                └────────── workspace/ShunyaGame (the game repo) ─────┘
```

One Python package (`shunya`) holds the spec's `core/`, `tools/`, `knowledge/`, `shared/` and the three backend apps. They are sub-packages rather than top-level folders only because `tools`, `core` and `shared` are too generic to be safe top-level Python import names; the boundaries are the same.

## Spec section → implementation

| Spec | Where | Notes |
|---|---|---|
| 5 Agent definition | `shared/schemas.py: AgentProfile`, `agents/**/*.yaml` | `enabled`, `capability`, `write_globs`, `avatar` added |
| 6 Runtime state machine | `core/agent_runtime/runner.py` | Limits checked before every model call; ends only via `submit_report` |
| 7 Company hierarchy | `agents/` | All 47 roles defined; 7 enabled |
| 8, 20, 48 Workflows | `core/orchestration/workflow.py` | One status-driven loop per task |
| 9 Task system | `core/task_engine/state_machine.py` | Adds `AWAITING_APPROVAL`, `REJECTED`, `BLOCKED`, `CANCELLED` |
| 10 Structured communication | `AgentMessage`, `core/orchestration/reports.py` | Handoffs, review feedback, bug reports, escalations |
| 11 Events | `core/events/bus.py`, `persistence/store.py: EventLog` | Every event persisted with a sequence number |
| 12, 13, 43 2.5D company | `apps/studio-ui/` | Renders `/studio/state` + `/ws/studio`; animation is local |
| 14 Meetings | `CollaborationSession`, `Orchestrator._plan_feature` | Producer drafts, programmer reviews feasibility, up to two rounds |
| 15 Provider abstraction | `core/interfaces.py: IModelProvider`, `core/models/` | The Anthropic SDK is imported in exactly one file |
| 16 Tools | `tools/` | 28 tools; registry enforces permission → schema → sandbox |
| 17, 18 Unreal Bridge | `bridge/client.py`, `unreal/.../ShunyaAgentBridge` | Editor and runtime scopes checked on both sides |
| 19 Git isolation | `tools/git_tools.py` | Worktree per task, merge only by orchestrator after approval |
| 21 Memory | `core/memory.py` | See the module docstring for where each memory kind lives |
| 22, 23 Retrieval, graph | `knowledge/` | Semantic + symbol + graph, fused by reciprocal rank |
| 24, 25 Database, Redis | `core/persistence/`, `RedisEventBus` | See ADR-005 |
| 26 API | `api/app.py` | All listed endpoints plus traces, costs, artifacts, messages |
| 27, 30 Permissions, guardrails | `core/permissions/engine.py` | Default deny |
| 28 Approvals | `core/orchestration/approvals.py` | Risk computed from facts |
| 29 Sandboxing | `WorkspaceSandbox` + worktrees | No shell tool exists |
| 31 Observability | `trace_id` on tasks, runs, tool calls, events; `/traces/{id}` | |
| 32 Cost control | `AgentProfile` budgets, `TaskBudget`, `CostRecord`, `/costs` | |
| 33 Model routing | `core/models/router.py` | Tier → model + effort |
| 34, 35 Prompts, context | `prompts/`, `PromptComposer`, briefs in `workflow.py` | Stable system prompt, task in the first user message |
| 36, 37 Artifacts, ADRs | `core/artifacts.py`, `docs/adr`, game `Docs/adr` | Versioned per task + type + title |
| 38, 39 QA, evidence | `_step_review`, `_step_build`, `_step_qa` | Evidence gate in code |
| 46 Deployment | `infrastructure/docker/` | |
| 50 Interfaces | `core/interfaces.py` | All eleven |

## What was added to the spec, and why

1. **Scripted model provider.** A deterministic `IModelProvider` that replays a screenplay for the first milestone. It lets the whole platform — worktrees, compiler, tests, gates, UI — be demonstrated, tested in CI and debugged for free, and makes pipeline tests exactly reproducible. It never pretends to be a model (`model="scripted-demo"`, cost 0) and declines requests it has no script for.

2. **The workflow is driven by persisted status** (ADR-002). This is what satisfies "task/company state survives application restart": there is no separate recovery path, the same loop runs again.

3. **Evidence gate.** A QA `PASS` is downgraded to `FAIL` by code when the test service did not record a passing run during that QA step, when QA's own criteria list contains an unmet item, or when a criterion has no evidence. The spec says agents should provide evidence; this makes it impossible not to.

4. **Risk is computed, not claimed.** `assess_risk` looks at the changed paths, deleted files, diff size, and whether the build and tests were actually verified.

5. **Protected paths are enforced twice.** The sandbox refuses writes to `Config/`, `*.Build.cs`, `*.Target.cs`, `*.uproject`; and before every commit, changes under those paths are reverted. The second check was added after the first real run showed the Unreal Editor rewriting `Config/*.ini` as a side effect of running tests.

6. **Reports through a tool.** Each role finishes by calling `submit_report` with a role-specific schema. One mechanism gives validated structured output on any provider and a natural end to the loop.

7. **`SKIPPED` and `ERROR` are first-class build/test outcomes.** No engine → `SKIPPED`, which raises approval risk to HIGH. Toolchain problems (timeouts, the Windows path limit) → `ERROR`, which escalates to a human instead of sending engineering in circles.

8. **Empty desks.** Roles that are defined but not implemented are `OFFLINE`; the office shows the desk, not a fake worker.

9. **Human controls beyond approve/reject.** Pause/resume a task or an agent, cancel, retry a blocked task with a guidance note, reject-with-rework.

10. **One task object per running pipeline.** API calls mutate the same in-memory task the pipeline saves, so a pause or a guidance note cannot be overwritten by the pipeline's next save.

## Known limits of V1

- The C++ index is regex-based. It understands Unreal's macros and conventions well enough for navigation and impact hints; it is not a compiler. `CppIndex` is the seam for libclang or tree-sitter.
- Embeddings are lexical hashes kept in memory (ADR-005).
- Store calls are synchronous inside the event loop. Fine for one studio on one machine; move them to a thread pool or an async driver before scaling.
- One Unreal process at a time (UnrealBuildTool's mutex), so builds and test runs queue even when tasks run in parallel.
- Agents cannot yet modify levels or assets: the bridge's editor commands exist, but no enabled role has `unreal_editor_modify`.
- The API has no authentication. It binds to `127.0.0.1`; do not expose it.
