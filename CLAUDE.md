# Shunya Studio AI — notes for Claude Code

Agentic game-studio backend (Python) + 2.5D web client + an Unreal game project the agents develop. Spec: `docs/SPEC.md`. How it maps to code: `docs/ARCHITECTURE.md`. Status of the 40-step plan: `docs/ROADMAP.md`.

## Commands (Windows, from the repo root)

```
.\.venv\Scripts\python -m pytest -q --timeout 120        # full suite, ~2 min, no Unreal / API key needed
.\.venv\Scripts\python -m pytest -q tests/test_core.py   # fast unit tests
.\.venv\Scripts\shunya serve                             # backend + UI at http://127.0.0.1:8400
.\.venv\Scripts\shunya demo --approve                    # one feature through the pipeline in the terminal
.\.venv\Scripts\shunya demo --approve --no-unreal        # same, without real compile/tests (seconds)
.\.venv\Scripts\shunya demo --approve "Build Orb Runner: an arena game"   # the 33-task all-departments run (about an hour with Unreal)
.\.venv\Scripts\python tools\dev\gen_agents.py           # regenerate agents/**/*.yaml (edit the script, not the YAML)
```

Compile the game template directly (UE 5.8 Launcher build):

```
"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" ShunyaGameEditor Win64 Development -project="<repo>\unreal\ShunyaGame\ShunyaGame.uproject" -waitmutex
```

## Rules that are easy to break

- **Authority stays in code.** Agents return reports; `core/orchestration/workflow.py` decides transitions. Do not let a prompt or a report field change task status directly.
- **Content agents send data, never code.** New asset kinds are a new typed job in `tools/content_tools.py` plus a handler in `tools/unreal_scripts/apply_content.py` (which runs inside the editor); do not add a way to pass Python through.
- **No shell tool, no merge tool.** New agent capabilities are typed tools in `shunya/tools/` with `required_permissions`, registered in `tools/registry.py`.
- **All agent file access goes through `WorkspaceSandbox.resolve`.** Never open a path from tool arguments directly.
- **Never report an unverified build or test as passed.** No engine → `SKIPPED`; toolchain failure → `ERROR`.
- **Only `core/models/anthropic_provider.py` imports a vendor SDK.** Everything else uses `IModelProvider`.
- **The UI never invents activity** and inserts backend text with `textContent` only (agent output is untrusted).
- `unreal/ShunyaGame` is the *template*. The studio works on a copy at `workspace/ShunyaGame` (its own git repo, branches `main` / `develop` / `agent/<TASK>`), created on first start. Change the template to change what new studios start from.
- Keep `workspace/` paths short: Unreal build output nests ~150 characters below a worktree and Windows allows 260.
- Do not round-trip source files through PowerShell `Get-Content` / `Set-Content`: it corrupts non-ASCII characters. Edit with Python or the editor tools.
- Tests use `FakeBuildService` / `FakeTestService` / `FakeContentService` / `FakePlaytestService` (`tests/conftest.py`) and the scripted provider; pipeline tests drive real git worktrees in a temp directory.

## Scripted screenplays

`shunya/demo/orb_runner/` holds the Orb Runner game the scripted provider can build: `files/<task>/` (C++ per code task), `docs/`, `content.py` (asset recipes), `screenplay.py` (the 33 steps and the scripted role behaviour). Each code step must compile on its own in order; verify changes by overlaying the steps on a copy of the template and compiling after each (see `code.apply_to`).

## Conventions

- Python 3.12+, Pydantic v2 models in `shared/schemas.py`, `from __future__ import annotations`, 4-space indent, line length ~160.
- Every state change publishes an `Event`; add new event types to `EventType` and handle them in `apps/studio-ui/studio.js: describe()` if they should appear in the activity feed.
- Unreal C++ follows Epic's conventions; game standards are in `unreal/ShunyaGame/Docs/CodingStandards.md` (agents retrieve that file).
