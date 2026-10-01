# ADR-002: The workflow is deterministic code driven by persisted task status

**Decision.** Agents never decide what happens next. Each pipeline turn reads `task.status` from the store and runs the step for that status; agents only return structured reports. Transitions are validated by the task state machine.

**Reason.** It makes the pipeline restartable (resume = run the loop again), auditable (every transition is an event with an actor and a reason), and keeps authority out of the LLM: a QA agent saying "PASS" cannot accept a task if the test service did not record a passing run during that QA step.

**Alternatives.** An LLM "manager" agent that routes work conversationally; a general workflow engine (Temporal, Prefect).

**Trade-offs.** New workflows are code changes, not prompt changes. A workflow engine would give durable timers and retries for free but is a heavy dependency for V1.

**Affected systems.** `shunya/core/orchestration/workflow.py`, `shunya/core/task_engine/`.
