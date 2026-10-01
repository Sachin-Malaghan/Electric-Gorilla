# Orb Runner - Animation brief

There are no skeletal characters in 0.1, so there is no rigging work. Motion is procedural code plus one cinematic.

## Orb idle (code: `USpinBobComponent`)
- Spin around the vertical axis at 90 degrees per second.
- Bob up and down on a sine wave: amplitude 18 units, 0.6 cycles per second.
- Starts at the rest position (offset 0 at time 0).
- The maths must be static functions so they can be tested without a world.

## Intro cinematic (content: `SEQ_Intro`, folder `Cinematics`)
One camera, 6 seconds at 30 fps, a slow descent toward the arena:
| Time | Location | Rotation (pitch, yaw, roll) |
|---|---|---|
| 0 s | -3200, -3200, 2600 | -33, 45, 0 |
| 3 s | -2600, 0, 2000 | -36, 0, 0 |
| 6 s | -1500, 0, 1700 | -50, 0, 0 |

The last frame roughly matches the gameplay camera so a cut into play is not jarring.
