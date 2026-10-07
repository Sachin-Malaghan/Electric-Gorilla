# Orb Runner - Controls and feel

## Controls
| Input | Action |
|---|---|
| W / Up arrow | Move north (+X), away from the camera |
| S / Down arrow | Move south (-X), toward the camera |
| D / Right arrow | Move east (+Y) |
| A / Left arrow | Move west (-Y) |

Keyboard only for 0.1.

## Feel rules
- Movement is immediate: no acceleration, no inertia. Speed is the tuning value (700).
- Diagonal movement is not faster than straight movement.
- Hitting a wall or pillar slides the player along it instead of stopping dead.
- The player cannot leave the arena (clamped to the half extent in `Tuning.md`).
- Input is ignored once the match is over.

## Camera
Third-person chase camera: behind the player looking north (+X), 950 units away, pitched down 28 degrees. It follows with slight lag and never rotates, so W is always "away from the camera".

## For QA tooling
The pawn must accept movement input from code as well as from the keyboard, so an automated bot can play a match.
