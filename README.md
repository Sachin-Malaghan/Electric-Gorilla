# Shunya Studio AI

A virtual game-development company: AI employees (management, engineering, QA, DevOps, â€¦) develop a **real Unreal Engine project**, and a **2.5D office** shows what each of them is really doing.

This repository is the V1 vertical slice from the [master architecture](docs/SPEC.md):

```
You â”€â–¶ Studio Director â”€â–¶ Producer â”€â–¶ Unreal Programmer â”€â–¶ Reviewer â”€â–¶ Build â”€â–¶ QA â”€â–¶ You approve â”€â–¶ merge
```

Type *"Create a simple Unreal health component."* and the studio plans it in a meeting, writes the C++ in an isolated git worktree, compiles it with UnrealBuildTool, fixes its own compile errors, runs Unreal automation tests, has it reviewed and independently QA'd with evidence, and asks you to approve the merge â€” while the avatars walk to the meeting room, type, compile and test.

## Run it

Requires Python 3.12+ and Git. Unreal Engine 5.4+ is optional (auto-detected under `C:\Program Files\Epic Games`); without it builds and tests are reported as **SKIPPED**, never as passed.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev,anthropic]"
.\.venv\Scripts\shunya serve
```

Open <http://127.0.0.1:8400>, type a feature request, and watch. Approve or reject under **Approvals**.

Terminal-only run of the whole pipeline:

```powershell
.\.venv\Scripts\shunya demo --approve
```

Tests (no Unreal or API key needed, about 2 minutes):

```powershell
.\.venv\Scripts\python -m pytest -q
```

### Scripted agents vs. real agents

| `SHUNYA_MODEL_PROVIDER` | What runs | Cost |
|---|---|---|
| `scripted` (default) | A fixed screenplay for the health-component milestone drives the *real* pipeline: real worktree, real compiler, real tests, real gates. Any other request is declined with a clear message. | free |
| `anthropic` | Real Claude agents with the same tools, permissions and budgets, for any request. Needs `ANTHROPIC_API_KEY` (or an `ant auth login` profile). | per-token, shown live in the UI |

Copy `.env.example` to `.env` to configure. Budgets per agent live in `agents/*.yaml`, per task in `TaskBudget`.

### With Unreal Editor open (optional)

Open `workspace/ShunyaGame/ShunyaGame.uproject` in the editor. The `ShunyaAgentBridge` plugin starts a localhost endpoint (`http://127.0.0.1:30777/shunya`, token in `Config/DefaultEngine.ini`) and the studio's Unreal tools (`get_editor_state`, `find_actor`, `spawn_actor`, `start_pie`, â€¦) and `/unreal/*` API start working. Compiling and testing do **not** need the editor open.

## What is in the box

| Path | What |
|---|---|
| `shunya/core/agent_runtime` | The bounded agent loop: iteration / time / token / cost / tool-call limits, repeated-error detection, pause, cancel, escalation |
| `shunya/core/orchestration` | The status-driven workflow, planning meetings, approvals with computed risk, structured report schemas |
| `shunya/core/task_engine` | Task state machine |
| `shunya/core/permissions` | Capability checks and the workspace sandbox (path validation, protected files) |
| `shunya/core/models` | `IModelProvider`, Claude provider, scripted provider, model routing, pricing |
| `shunya/core/persistence`, `events`, `memory.py`, `artifacts.py` | SQL store + append-only event log, event bus (in-memory / Redis), memory kinds, versioned artifacts |
| `shunya/tools` | Typed tools: files, git worktrees, C++ index, compile, automation tests, Unreal bridge. No shell. |
| `shunya/knowledge` | C++ symbol index, dependency / call graph, hybrid retrieval |
| `shunya/bridge`, `unreal/ShunyaGame/Plugins/ShunyaAgentBridge` | Unreal Bridge client and the editor plugin |
| `shunya/api`, `apps/studio-ui` | REST + WebSocket API and the 2.5D studio client |
| `agents/`, `prompts/` | 47 employee definitions (7 active in V1) and layered prompts |
| `unreal/ShunyaGame` | Template of the game project the studio develops |
| `tests/` | 50 tests: state machine, sandbox, runtime limits, full pipeline, restart recovery, API |
| `docs/` | [Architecture](docs/ARCHITECTURE.md) Â· [Roadmap](docs/ROADMAP.md) Â· [ADRs](docs/adr) Â· [original spec](docs/SPEC.md) |

Runtime state lives in `data/` (database, artifacts) and `workspace/` (the working game repo and task worktrees); both are git-ignored. Delete them to start from a clean studio.

## Honest status

Verified on the development machine (Windows 10, UE 5.8, Python 3.13):

- The scripted pipeline end to end with the **real** engine: real compile error caught, parsed and fixed; real build; 5/5 real Unreal automation tests run by the programmer and again by QA; approval; merge into `develop`.
- The `ShunyaGame` template and both `ShunyaAgentBridge` modules compile on UE 5.8.
- The automated test suite.
- The 2.5D client against a live run.

Not yet exercised:

- **Real Claude agents end to end** â€” the provider is implemented against the current SDK but no paid run was made. Expect prompt tuning.
- **The bridge plugin's HTTP routes against a running editor** â€” it compiles; the routes have not been called live.
- **Docker Compose / PostgreSQL / Redis** â€” written, not run (no Docker on the dev machine). SQLite + in-process bus is what has been tested.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the 40-step plan and where each step stands.
