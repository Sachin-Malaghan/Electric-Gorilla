# ADR-001: Modular monolith, three separate products

**Decision.** The studio backend is one Python process (FastAPI + orchestrator + agent runtime) with strict internal module boundaries. The 2.5D studio client and the Unreal game project are separate products that talk to it only through REST/WebSocket and the Unreal Bridge.

**Reason.** One developer machine, one Unreal Editor, a handful of concurrent agents. Process boundaries would add failure modes without adding capacity. The spec (sections 2, 45, 46) asks for exactly this.

**Alternatives.** Microservices per subsystem; a queue-driven worker fleet.

**Trade-offs.** A crash takes everything down - mitigated by persisting all state and resuming pipelines from task status on restart. Scaling out later means moving the orchestrator's jobs behind the Redis queue; the `IEventBus` / `ITaskRepository` interfaces are the seams.

**Affected systems.** Everything under `shunya/`.
