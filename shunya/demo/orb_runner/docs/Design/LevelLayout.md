# Orb Runner - Level layout: L_Arena

Unreal units (cm). Origin at the arena centre, +X is "north" (up the screen), +Y is "east". Basic shapes are 100 units across before scaling.

## Structure
| Element | Shape | Location (x, y, z) | Scale (x, y, z) |
|---|---|---|---|
| Floor | Plane | 0, 0, 0 | 40, 40, 1 |
| Wall North | Cube | 2000, 0, 150 | 1, 41, 3 |
| Wall South | Cube | -2000, 0, 150 | 1, 41, 3 |
| Wall East | Cube | 0, 2000, 150 | 41, 1, 3 |
| Wall West | Cube | 0, -2000, 150 | 41, 1, 3 |
| Pillars 1-4 | Cylinder | (+-800, +-800, 200) | 2, 2, 4 |

## Gameplay actors
| Actor | Location |
|---|---|
| Player start | 0, 0, 60 |
| Orbs 1-4 (edges) | (1400, 0, 80), (-1400, 0, 80), (0, 1400, 80), (0, -1400, 80) |
| Orbs 5-8 (corners) | (+-1300, +-1300, 80) |
| Chaser drone | -1700, 1700, 90 |

## Intent
- The player starts in the centre with every orb equally far away: the first decision is the route.
- Pillars sit between the centre and the corner orbs, so reaching a corner means going around something.
- The drone starts in a corner, far from the player: the first seconds are safe.

## Level settings
Game mode override: `OrbGameMode`. No baked lighting.
