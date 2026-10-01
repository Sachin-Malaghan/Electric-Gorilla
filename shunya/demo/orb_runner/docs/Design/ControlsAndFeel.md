# Orb Runner - Controls and feel

## Controls
| Input | Action |
|---|---|
| W / Up arrow | Move north (+X) |
| S / Down arrow | Move south (-X) |
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
Follows the player with slight lag (smooth, never rotates), 1700 units away, pitched down 62 degrees.

## For QA tooling
The pawn must accept movement input from code as well as from the keyboard, so an automated bot can play a match.
