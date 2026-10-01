# Orb Runner - Art style guide

## The rule
The world is dark and matte; anything the player must react to emits light. If it does not matter to play, it does not glow.

## Palette (linear RGB, 0-1)
| Name | RGB | Used for |
|---|---|---|
| Navy | 0.03, 0.05, 0.10 | Floor base |
| Grid cyan | 0.10, 0.55, 0.75 | Floor grid lines |
| Slate | 0.16, 0.19, 0.27 | Walls |
| Violet | 0.30, 0.22, 0.52 | Pillars |
| Orb cyan | 0.20, 0.90, 1.00 | Orbs (emissive) |
| Amber | 1.00, 0.60, 0.10 | Player (slightly emissive) |
| Drone red | 0.90, 0.10, 0.15 | Drone (emissive) |

## Materials
| Asset | Folder | Base | Emissive | Metallic / roughness |
|---|---|---|---|---|
| `M_Floor` | Environment | `T_FloorGrid` (navy with grid-cyan lines), tiled 10x | none | 0 / 0.85 |
| `M_Wall` | Environment | Slate | none | 0.2 / 0.7 |
| `M_Pillar` | Props | Violet | none | 0.3 / 0.5 |
| `M_Orb` | Props | Orb cyan | Orb cyan x 14 | 0 / 0.2 |
| `M_Player` | Characters | Amber | Amber x 1.5 | 0.7 / 0.3 |
| `M_Drone` | Characters | Drone red | Drone red x 6 | 0.4 / 0.4 |

## Emissive ranking (brightest first)
Orbs > drone > player > nothing else. Never give environment materials an emissive term.

## Shapes
Engine basic shapes only for 0.1: sphere (player, orbs), cone (drone), cylinder (pillars), cube (walls), plane (floor).
