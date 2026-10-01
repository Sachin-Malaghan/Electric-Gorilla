# Orb Runner - Game Design Document

## One line
Roll around a small neon arena and recover every orb before the clock runs out, while a drone hunts you.

## Pillars
1. **Readable in one glance.** Dark arena, bright things matter: orbs glow cyan, the drone glows red, you are amber.
2. **One verb.** You move. Everything else (collecting, dodging) comes from where you move.
3. **A match is one minute.** Win or lose quickly, try again.

## Core loop
Spawn in the centre -> pick a route through the orbs -> avoid the drone -> last orb collected = win. Time out or lose all hull = lose.

## Rules
- The arena is a 4000 x 4000 unit square with walls and four pillars.
- There are 8 orbs. Touching an orb collects it and scores points.
- The match is won the moment the last orb is collected.
- The match is lost when the timer reaches zero or the player's hull (health) reaches zero.
- Once the match is over nothing changes any more: no score, no damage, no movement.
- One drone chases the player. Contact damages the hull on a cooldown.

## Camera and presentation
Fixed-angle camera above and behind the player, looking down at about 60 degrees. HUD: score, orbs left, time, hull bar, and a banner when the match ends.

## Out of scope for 0.1
Menus, restart flow, multiple levels, power-ups, more than one drone, gamepad support.

## Other documents
Numbers: `Tuning.md`. The drone: `ThreatSpec.md`. The arena: `LevelLayout.md`. Controls: `ControlsAndFeel.md`. Text: `Narrative.md`.
