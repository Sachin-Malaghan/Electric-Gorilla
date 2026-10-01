# ADR-004: Agents get typed tools, not a shell

**Decision.** Every capability is a tool with a Pydantic input schema and a list of required permissions. There is no shell tool. Compiling and testing are `compile_project` and `run_automation_tests`, which run fixed UnrealBuildTool / UnrealEditor-Cmd command lines on the agent's worktree and return parsed results.

**Reason.** A shell makes path validation, permission checks and budgets unenforceable. Typed tools make every action observable (one `ToolCallRecord` and one event each) and let the 2.5D office show what an agent is really doing.

**Alternatives.** A sandboxed shell in a container; an allow-listed command runner.

**Trade-offs.** New capabilities need a new tool. That friction is the point.

**Affected systems.** `shunya/tools/`, `shunya/core/permissions/`.
