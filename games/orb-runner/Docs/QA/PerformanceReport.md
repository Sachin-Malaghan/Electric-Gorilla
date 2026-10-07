# Performance report - L_Arena

Run `T-eda0dad370`, 1280x720 windowed, development editor build (`-game`). Budget: average of at least 30 FPS. Verdict: **PASSED**.

| Measure | Value |
|---|---|
| Average FPS | 57.8 |
| Worst frame | 400.0 ms |
| Measured for | 14.6 s |

## Checks
```
[PASS] Playtest.L_Arena.BotCompletesTheMatch - result=WIN
[PASS] Playtest.L_Arena.BotWins - score=80 orbs_remaining=0 health=100
[PASS] Playtest.L_Arena.AverageFpsAtLeast30 - avg_fps=57.8 worst_frame_ms=400.0
[PASS] Playtest.L_Arena.ScreenshotCaptured - artifact=ART-813191e820
```

## Notes
Measured from one second after the match starts, so start-up hitches are excluded from the average; the worst frame still includes shader warm-up. A packaged build would be faster than this editor-hosted run.
