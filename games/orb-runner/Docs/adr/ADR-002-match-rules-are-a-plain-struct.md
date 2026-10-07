# ADR-002: Match rules are a plain struct, not an actor

**Decision.** Score, orbs remaining, the countdown and the win/lose state live in `FOrbRules`, a plain `USTRUCT` with no dependency on a world. `AOrbGameMode` owns one and forwards events to it. The same approach is used for every rule that can be expressed as a function: movement, steering, HUD formatting and the QA bot's decisions are static functions on their classes.

**Reason.** The studio verifies work with headless automation tests (no map, no rendering). Logic that needs a world cannot be asserted there; logic in plain functions can. It also keeps actors thin and makes the tuning document directly checkable.

**Alternatives.** Rules inside the game mode's tick; a `GameState` subclass with replicated fields.

**Trade-offs.** The rules are not replicated - acceptable for single-player 0.1. A multiplayer version would move the struct into a replicated `GameState` (see ADR-001) without changing the logic.

**Affected systems.** `Game/`, and by convention every gameplay class in the module.
