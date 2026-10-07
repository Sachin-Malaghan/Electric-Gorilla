# Orb Runner - Environment brief

## Level: `L_Arena` (folder `Maps`)
Build exactly what `Docs/Design/LevelLayout.md` specifies - shapes, locations and scales are in its tables. Materials from the style guide: floor `M_Floor`, walls `M_Wall`, pillars `M_Pillar`. Gameplay actors by class: orbs `/Script/ShunyaGame.OrbCollectible`, drone `/Script/ShunyaGame.ChaserDrone`. Game mode `/Script/ShunyaGame.OrbGameMode`.

Label every actor so the level can be checked by name: `Floor`, `Wall North/South/East/West`, `Pillar 1-4`, `Orb 1-8`, `Chaser Drone`, `Player Start`.

## Lighting pass (separate task, after the level exists)
Fully dynamic - nothing to bake.
| Actor | Label | Settings |
|---|---|---|
| Directional light | Key Light | pitch -48, yaw 35, intensity 3.5, cool white (0.80, 0.86, 1.0) |
| Sky light | Sky Fill | intensity 0.7, real-time capture |
| Sky atmosphere | Sky Atmosphere | defaults |
| Post process (unbound) | Exposure | fixed exposure, brightness 1.0, so the emissive ranking in the style guide holds |
| 4 point lights | Corner Glow 1-4 | at (+-1700, +-1700, 320), violet (0.45, 0.3, 0.9), intensity 600, radius 1100 |

## Acceptance
The level opens, has the `OrbGameMode` override, 8 orbs, 1 drone, 1 player start, and no mesh without a material.
