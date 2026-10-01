# Roadmap — the spec's 40 implementation steps

Legend: ✅ built and tested · 🟡 built, not fully exercised (see note) · ⬜ not started

| # | Step | Status | Note |
|---|---|---|---|
| 1 | Monorepo and Python backend | ✅ | |
| 2 | PostgreSQL and Redis infrastructure | 🟡 | Compose file + `DATABASE_URL` / `REDIS_URL` support written; only SQLite + in-process bus tested |
| 3 | Agent, Task, Run, Tool, Artifact, Event models | ✅ | `shared/schemas.py` |
| 4 | Model-provider abstraction | ✅ | |
| 5 | One bounded single-agent loop | ✅ | `test_runtime.py` |
| 6 | Tool registry | ✅ | |
| 7 | Safe filesystem tools | ✅ | |
| 8 | Git tools and isolated task workspaces | ✅ | |
| 9 | Task state machine | ✅ | |
| 10 | Studio Director / Producer basics + one Programmer | ✅ | Two programmers |
| 11 | Structured manager-to-worker delegation | ✅ | `AgentMessage` handoffs |
| 12 | WebSocket event stream | ✅ | Replay from any sequence number |
| 13 | Crude 2.5D client with two employees | ✅ | Web client, seven active employees |
| 14 | Bind real backend states to avatars | ✅ | |
| 15 | Unreal Bridge | 🟡 | Client + tools written; not called against a live editor |
| 16 | ShunyaAgentBridge editor plugin | 🟡 | Compiles on UE 5.8; HTTP routes not exercised live |
| 17 | Compile / build tools | ✅ | Real UnrealBuildTool run verified |
| 18 | Unreal Programmer agent | 🟡 | Verified with the scripted provider; real-model run pending |
| 19 | Independent Reviewer | 🟡 | same |
| 20 | QA agent | 🟡 | same |
| 21 | Unreal automated testing | ✅ | Real headless Automation Framework run verified |
| 22 | PostgreSQL project memory | 🟡 | Memory store works (on SQLite); seeded from the game's `Docs/` |
| 23 | Document / code RAG | ✅ | Hashing embedder; swap for a real one behind `IEmbedder` |
| 24 | C++ symbol index | ✅ | Regex-based |
| 25 | Dependency / call graph | ✅ | Approximate call graph |
| 26 | Producer task decomposition | 🟡 | Multi-task plans with dependencies supported and scheduled; only single-task plans exercised |
| 27 | Design department | ⬜ | Roles defined, disabled |
| 28 | Environment department | ⬜ | Needs `unreal_editor_modify` roles + bridge commands in anger |
| 29 | Art pipeline | ⬜ | Needs `Content/AI_Staging` promotion flow |
| 30 | Animation and Audio | ⬜ | |
| 31 | Performance testing | ⬜ | Telemetry subsystem exists in the plugin |
| 32 | Approval system | ✅ | |
| 33 | Budget / cost system | ✅ | Per agent run and per task; ledger at `/costs` |
| 34 | Permissions and guardrails | ✅ | |
| 35 | Tracing / monitoring | 🟡 | Trace ids + `/traces/{id}`; no external exporter (OpenTelemetry) yet |
| 36 | CI/CD | 🟡 | GitHub Actions workflow for the Python suite; no Unreal CI |
| 37 | Failure recovery / escalation | ✅ | Bounded fix loops, escalation to supervisor, human retry |
| 38 | Persistent company state and restart recovery | ✅ | `test_pipeline.py` restart tests |
| 39 | Polish 2.5D company simulation | ⬜ | Unreal 2.5D client (spec 42) not started; pathfinding is straight-line |
| 40 | Production hardening and security review | ⬜ | API has no auth; localhost only |

## V1 acceptance criteria (spec 49)

All seventeen are covered by tests in `tests/test_pipeline.py`, `tests/test_runtime.py` and `tests/test_api_and_knowledge.py`, using the scripted provider. "Programmer can inspect Unreal C++", "compiled through a controlled tool", "compilation failures are captured and parsed", "bounded corrections" and "automated tests can execute" were additionally verified against the real UE 5.8 toolchain.

## Suggested next steps, in order

1. **Run the milestone with real agents** (`SHUNYA_MODEL_PROVIDER=anthropic`), read the traces, tune `prompts/`. Start with a low `cost_budget` in `agents/engineering/engineering.yaml`.
2. Exercise the bridge plugin against a running editor; add a QA step that plays the feature in PIE and captures telemetry.
3. A second milestone that needs two dependent tasks, to exercise the task graph for real.
4. Bring up PostgreSQL + Redis with the compose file; move store calls off the event loop.
5. Design department (step 27): the Lead Designer produces a specification artifact the Producer plans from.
