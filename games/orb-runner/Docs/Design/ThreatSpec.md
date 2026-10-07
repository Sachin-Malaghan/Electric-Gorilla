# Orb Runner - Threat specification: the Chaser Drone

## Behaviour
- The drone always moves straight toward the player's current position, on the ground plane, at its speed (see `Tuning.md`: 260).
- It never overshoots: if the player is closer than one frame of movement, it stops on the player.
- It ignores walls and pillars (it hovers). This is deliberate: pillars are cover for the player's line of travel, not for the drone.
- It does nothing once the match is over.

## Damage
- When the drone is within 130 units of the player it deals contact damage (25), then waits for its cooldown (1.0 s) before it can hit again.
- Damage goes through the player's health component, so the normal death rule applies.

## Feel targets
- A player who keeps moving is never caught.
- A player who stops to think for three seconds is in trouble.

## Testable statements
1. One second of pursuit moves the drone 260 units toward the target.
2. The drone stops on the target instead of passing it.
3. The drone's speed is lower than the player's speed.
4. A second hit is impossible inside the cooldown.
