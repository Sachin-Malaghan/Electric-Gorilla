# Orb Runner 0.1 - manual and reference

## Play
Open `ShunyaGame.uproject`, load `/Game/Shunya/Maps/L_Arena`, press Play. Or from a command line:

```
UnrealEditor.exe ShunyaGame.uproject /Game/Shunya/Maps/L_Arena -game -windowed
```

Move with **WASD** or the arrow keys. Collect all 8 orbs within 60 seconds. The red drone drains your hull on contact; four hits end the run.

## What is on screen
`SCORE` and `ORBS LEFT`, `TIME`, the `HULL` bar, and at the end `ALL ORBS RECOVERED` or `SIGNAL LOST`.

## Class reference (module `ShunyaGame`)
| Class | Header | What it does |
|---|---|---|
| `FOrbRules` | `Game/OrbRules.h` | Match state: `Start`, `CollectOrb`, `Tick`, `PlayerDied`, `IsOver` |
| `AOrbGameMode` | `Game/OrbGameMode.h` | Owns the rules; `RegisterOrb`, `NotifyOrbCollected`, `NotifyPlayerDied`, `OnMatchEnded` |
| `UHealthComponent` | `Components/HealthComponent.h` | `ApplyDamage`, `Heal`, `OnDeath` / `OnDeathNative`; replicated |
| `USpinBobComponent` | `Animation/SpinBobComponent.h` | Spin and bob for pickups; `ComputeBobOffset`, `ComputeYaw` |
| `AOrbRunnerPawn` | `Player/OrbRunnerPawn.h` | Player; `SetExternalMoveInput`, `ComputeMoveDelta`, `ClampToArena` |
| `AOrbCollectible` | `Pickups/OrbCollectible.h` | Orb worth `Value` points |
| `AChaserDrone` | `AI/ChaserDrone.h` | Pursuit; `ComputeSteer`, `CanDamage` |
| `AOrbHUD` | `UI/OrbHUD.h` | HUD; `FormatTime`, `FormatBanner`, `FormatScoreLine` |
| `UOrbPlaytestSubsystem` | `Tools/OrbPlaytestSubsystem.h` | QA bot; `PickNearest`, `ComputeBotInput` |

## Automated checks
- Unit tests: run the automation tests with the filter `ShunyaGame` (headless: `-ExecCmds="Automation RunTests ShunyaGame; Quit" -nullrhi`).
- Playtest: add `-ShunyaAutoPlay` to the play command line. A bot plays the match, `Saved/Screenshots/Playtest.png` is written, and the log gets one line starting `ShunyaPlaytest:` with the result, score, time and frame rate.

## Content
Materials, sounds, the level and the intro sequence are under `/Game/Shunya`. Their recipes are under `ContentJobs/` and can be rebuilt from there.

## Known limits
Keyboard only. No restart flow: close and relaunch. The intro sequence `SEQ_Intro` exists but is not yet triggered by the game.
