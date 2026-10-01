# Orb Runner 0.1.0 - release notes

First playable build, on the `develop` branch.

## What is in it
- One level, `L_Arena`: a walled neon arena with four pillars.
- The player probe (WASD / arrows), eight orbs, one chaser drone.
- Match rules: 60 second timer, 10 points per orb, win on the last orb, lose on timeout or zero hull.
- HUD with score, orbs left, timer, hull bar and result banner.
- Sound effects for pickup, hit, win and lose, and a looping music track.
- An intro camera sequence (`SEQ_Intro`), not yet triggered by the game.
- A QA autoplay bot (`-ShunyaAutoPlay`) that plays a match and reports the result.

## Verification
See `Docs/QA/SignOff.md`. In short: the full automation suite passes, the bot wins a match on `L_Arena`, and the frame-rate budget is met on the development machine.

## Known limits
Keyboard only; no menus or restart; single level; the drone ignores obstacles by design.

## Not done / next
Trigger the intro sequence at match start; a restart flow; gamepad input; a second level.

## Promotion to `main`
This build is on `develop`. Promoting it to `main` is a release decision for the studio owner and has not been done.
