# ADR-001: Gameplay state lives in replicated, server-authoritative components

**Decision.** Reusable gameplay state (health, stamina, inventory, ...) is implemented as `UActorComponent` subclasses in the `ShunyaGame` module, replicated by default and mutated only on the authority. Components expose Blueprint-readable state, Blueprint-callable mutators that validate input, and multicast delegates for changes - plus a native delegate when C++ code or tests need to listen.

**Reason.** The game is planned as multiplayer. Putting state in components keeps characters thin, lets any actor opt in, and keeps each piece testable headless with `NewObject`.

**Alternatives.** State on the character class; the Gameplay Ability System (to be reconsidered when abilities and effects arrive - that would be a new ADR).

**Trade-offs.** More small classes; replication must be considered for every new piece of state.

**Affected systems.** Everything under `Source/ShunyaGame/Public/Components`.
