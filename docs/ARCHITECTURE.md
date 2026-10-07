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

## All departments: three tracks through one pipeline

Every task carries a `track`, chosen by the Producer, and the same status-driven loop handles all three:

| Step | `code` | `doc` | `content` |
|---|---|---|---|
| Author | a programmer (C++, compile, tests) | a designer / lead / writer (`create_doc`), sometimes after a verification run | an artist (`queue_*` jobs, then `apply_content`) |
| Review | Technical Director | the department lead named in the plan | the department lead named in the plan |
| Build | Build Engineer compiles | not applicable | not applicable |
| QA | QA runs the automation tests | code checks the document exists and, if the task demands one, that a passing verification run is recorded | QA runs `validate_content` in the editor |
| Before approval | - | - | assets are promoted from `/Game/AI_Staging` to `/Game/Shunya` |
| Approval | human, or policy when the computed risk is LOW and the owner enabled that | same | same |

**Content tools (spec 40, 41).** Art, environment, animation and audio agents never send Python to the editor. They queue typed jobs (texture, material, sound, level, level additions, sequence) that are saved as JSON recipes under `ContentJobs/<task>/` in the worktree, and one headless editor session runs the studio-owned `shunya/tools/unreal_scripts/apply_content.py` with those jobs as data. Textures, images and sounds are generated procedurally by `shunya/tools/content/generators.py` (pure standard library) - these stand in for external generators and sit behind the same tools. Assets land in `/Game/AI_Staging`; the lead reviews the recipes, QA validates the assets, and only then does the orchestrator promote them. Edits to an existing asset (a lighting pass on a level) are made in place on the task branch - the branch is the isolation.

**Playtests as evidence.** `run_playtest` launches the real game with `-ShunyaAutoPlay`; the game's own QA subsystem plays the match, captures a screenshot and logs one `ShunyaPlaytest:` JSON line. The tool records the result as a verification run (so the same evidence gate applies) and stores the screenshot as an artifact that appears on the approval.

**Build reuse.** Worktrees whose code is identical to `develop` copy the develop checkout's binaries instead of compiling (`ToolServices.ensure_built`, keyed by a hash of the sources), so content and QA tasks do not pay for a compile each.

**Approval policy.** `SHUNYA_AUTO_APPROVE_MAX_RISK=LOW` (or the checkbox in the Approvals tab) lets policy approve merges whose computed risk is LOW. Anything else still waits for the owner. A 33-task feature would otherwise need 33 clicks.

**The Orb Runner screenplay** (`shunya/demo/orb_runner/`) is the scripted provider's second request: 33 tasks that give 31 employees across all nine departments real work - design documents, C++ in six steps, materials, sounds, a level, lighting, a cinematic, a playtest, a performance check, a regression run, a sign-off, a manual and release notes. Nine roles have nothing real to do in a game this small and stay offline (rigging, VFX, landscape, foliage, optimisation, graphics, networking, CI, crash investigation).

## Games as folders

A request names a game (explicitly, or derived from its text). `GameRegistry` creates `workspace/games/<slug>/` from the template as an independent git repository the first time, and continues it afterwards; folders found on disk are adopted on start, so the folders are the source of truth. Every task carries `game_id`, worktrees stay in the short shared `workspace/wt/` directory, and packaged builds go to `workspace/builds/<slug>/`. When a request finishes, `GamePublisher` exports the game's `develop` snapshot into `games/<slug>/` of the studio repository and commits exactly that folder (optionally pushing), so finished games are versioned next to the studio.

## Operating it (see [DEPLOYMENT.md](DEPLOYMENT.md))

- **Model key and cap.** The page asks for the Anthropic key when none is configured (`.env` is the back door); it is stored server-side and write-only. A studio-wide spending cap stops model calls when reached.
- **Access.** `SHUNYA_API_TOKEN` puts every route and the WebSocket behind one shared token (header, cookie or query); `/health` stays open. The server refuses to listen on a non-loopback address without it.
- **Process trees.** Every process the studio starts is registered in `core/processes.py` and killed as a tree on timeout, cancellation and shutdown. Before this, cancelling a task could leave UnrealBuildTool's compilers running.
- **Logs and health.** Rotating `data/logs/studio.log` with an access line per request; `/health` for liveness, `/system` for the owner.
- **Limits.** `SHUNYA_MAX_ACTIVE_FEATURES` bounds feature requests in flight (HTTP 429 beyond it).
- **`shunya doctor` / `shunya backup`.** Preflight checks for the machine; an online copy of the database plus artifacts.
- **Packaging.** `package_game` runs Unreal Automation Tool (build, cook, stage, pak), then starts the packaged executable with the QA bot and records the result as a verification run. The task that records a packaged build is always HIGH risk, so it always reaches the owner.

Two defects were found by running this for real and are now guarded against: packaging wrote log files into the worktree that rode along into the commit (now excluded), and assets the game loads by path were missing from the packaged build because no map references them (the game folder is now always cooked, and the playtest reports missing runtime content as a failed check).

## Known limits of V1

- The C++ index is regex-based. It understands Unreal's macros and conventions well enough for navigation and impact hints; it is not a compiler. `CppIndex` is the seam for libclang or tree-sitter.
- Embeddings are lexical hashes kept in memory (ADR-005).
- Store calls are synchronous inside the event loop. Fine for one studio on one machine; move them to a thread pool or an async driver before scaling.
- One Unreal process at a time (UnrealBuildTool's mutex), so builds and test runs queue even when tasks run in parallel.
- Agents cannot yet modify levels or assets: the bridge's editor commands exist, but no enabled role has `unreal_editor_modify`.
- API access is one shared token, no users or roles, no built-in TLS.
