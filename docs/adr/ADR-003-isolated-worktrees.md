# ADR-003: One git worktree per task; agents never touch main; merges need a human

**Decision.** The game lives in its own git repository (`workspace/ShunyaGame`, created from `unreal/ShunyaGame`). Every task gets branch `agent/<TASK-ID>` and a worktree under `workspace/wt/<TASK-ID>`. Agents write only inside their worktree, only to their writable globs, never to protected paths (`Config/`, `*.Build.cs`, `*.Target.cs`, `*.uproject`). No agent has a merge tool; the orchestrator merges into `develop` after a human approval. `main` is only ever changed by a human.

**Reason.** Isolation makes a bad agent run cheap to discard, lets tasks run in parallel, and makes "what did the agent change" a plain `git diff develop`.

**Alternatives.** Containers per agent; a shared working copy with file locks.

**Trade-offs.** Each worktree compiles the project modules from scratch (about two minutes for a small project). Worktree paths must stay short on Windows: Unreal's build output nests about 150 characters below the worktree root and the limit is 260.

**Affected systems.** `shunya/tools/git_tools.py`, `shunya/core/permissions/`, the build and test tools.
