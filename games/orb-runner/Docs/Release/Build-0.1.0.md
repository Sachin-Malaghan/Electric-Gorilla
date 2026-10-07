# Packaged build 0.1.0 - Windows (Development)

Packaging run `T-87299e9f54`. Verdict: **PASSED**.

| | |
|---|---|
| Location | `C:\SACHIN\AI Company\workspace\builds\v0.1.0` |
| Executable | `C:\SACHIN\AI Company\workspace\builds\v0.1.0\Windows\ShunyaGame.exe` |
| Size | 898.4 MB in 48 files |
| Packaging time | 447.5 s |
| Smoke run | WIN - score 80, 58.1 FPS average |

## Checks
```
[PASS] Package.BuildCookStageSucceeded - 898.4 MB in 48 files
[PASS] Package.ExecutableStartsAndBotFinishesAMatch - {"result": "WIN", "score": 80, "orbs_remaining": 0, "time_remaining": 45.4, "health": 100, "seconds": 14.6, "avg_fps": 58.1, "worst_frame_ms": 272.4, "map": "L_Arena"}
[PASS] Package.BotWinsInThePackagedGame - score=80 avg_fps=58.1
```

## How to run
Start the executable above. No Unreal Engine installation is needed on the machine that runs it.

## Notes
This is a Development configuration build (logging and the QA bot are included); a Shipping build is a later step. The build is not stored in git. 
