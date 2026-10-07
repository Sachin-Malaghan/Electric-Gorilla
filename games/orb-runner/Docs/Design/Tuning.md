# Orb Runner - Tuning

All numbers engineering must implement. Distances in Unreal units (cm), time in seconds.

| Value | Number | Why |
|---|---|---|
| Time limit | 60 | One-minute matches (GDD pillar 3) |
| Orbs in the level | 8 | A full clear takes 20-30 s for a good route, leaving room for mistakes |
| Points per orb | 10 | Perfect score is 80 |
| Player health (hull) | 100 | |
| Player speed | 700 | Crosses the arena in under 6 s |
| Drone speed | 260 | Clearly slower than the player: you can always escape |
| Drone contact damage | 25 | Four hits end the match |
| Drone damage cooldown | 1.0 | Standing next to the drone is not instantly fatal |
| Arena half extent for the player | 1850 | Keeps the player off the walls |

## Rules that follow from the numbers
- Score only ever goes up, by exactly the orb's value.
- The timer never shows a negative value.
- Winning freezes the timer; the remaining time is shown.
