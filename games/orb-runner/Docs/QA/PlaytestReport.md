# Playtest report - L_Arena

Run `T-a9291f9fca` on `L_Arena` with the QA bot (`-ShunyaAutoPlay`). Verdict: **PASSED**.

| Measure | Value |
|---|---|
| Match result | WIN |
| Score | 80 of 80 |
| Orbs remaining | 0 |
| Time remaining | 45.4 s |
| Hull remaining | 100 |
| Match length | 14.6 s |
| Average FPS | 55.9 |
| Screenshot artifact | ART-0ceba9a5ab |

## Checks
```
[PASS] Playtest.L_Arena.BotCompletesTheMatch - result=WIN
[PASS] Playtest.L_Arena.BotWins - score=80 orbs_remaining=0 health=100
[PASS] Playtest.L_Arena.AverageFpsAtLeast20 - avg_fps=55.9 worst_frame_ms=400.0
[PASS] Playtest.L_Arena.ScreenshotCaptured - artifact=ART-0ceba9a5ab
```

## Notes
The bot takes the nearest orb each time and steers away from the drone inside 420 units. A human player was not involved in this run.
