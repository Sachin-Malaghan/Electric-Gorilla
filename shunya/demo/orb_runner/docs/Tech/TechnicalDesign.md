# Orb Runner - Technical design

Everything lives in the `ShunyaGame` module. No new module dependencies are needed (`Engine`, `NetCore` are already there).

## Classes
| Class | Folder | Responsibility |
|---|---|---|
| `FOrbRules` (struct) | `Game/` | Score, orbs remaining, countdown, match state. Pure logic, no actors - fully unit-testable. |
| `AOrbGameMode` | `Game/` | Owns one `FOrbRules`, ticks it, receives notifications, announces the result, plays music and result cues. |
| `UHealthComponent` | `Components/` | Hull. Replicated, server-authoritative (ADR-001). |
| `USpinBobComponent` | `Animation/` | Procedural idle motion for pickups. Static maths functions for tests. |
| `AOrbRunnerPawn` | `Player/` | Player sphere, camera, keyboard movement, external input for bots. Static movement maths. |
| `AOrbCollectible` | `Pickups/` | Orb: trigger sphere, glow, registers with the game mode, notifies on overlap. |
| `AChaserDrone` | `AI/` | Pursuit and contact damage. Static steering maths. |
| `AOrbHUD` | `UI/` | Canvas HUD. Static formatting functions. |
| `UOrbPlaytestSubsystem` | `Tools/` | QA bot behind `-ShunyaAutoPlay`: plays, screenshots, logs a `ShunyaPlaytest:` JSON line, exits. |

## Rules
- **Logic in static or plain functions, actors stay thin.** Every tuning rule must be assertable in a headless automation test with no world.
- **Order independence.** Orbs register with the game mode in `BeginPlay`; the game mode must not assume it begins play before or after them.
- **Content is optional at runtime.** Code looks up materials and sounds by path under `/Game/Shunya/...` and must run correctly when they are missing.
- **Build order.** Rules + health -> idle animation -> player and orbs -> drone -> HUD -> QA bot. Each step compiles and passes its own tests.

## Asset paths the code expects
`/Game/Shunya/Characters/M_Player`, `M_Drone`; `/Game/Shunya/Props/M_Orb`; `/Game/Shunya/Audio/S_Pickup`, `S_Hit`, `S_Win`, `S_Lose`, `S_MusicLoop`; map `/Game/Shunya/Maps/L_Arena`.

## Test path prefixes
`ShunyaGame.Health`, `.Rules`, `.Animation`, `.Player`, `.Orb`, `.AI`, `.UI`, `.Tools`.
