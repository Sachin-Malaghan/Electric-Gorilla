# Project: ShunyaGame

ShunyaGame is the Unreal Engine 5 C++ game the studio is building. Layout, relative to the project root:

- `ShunyaGame.uproject` - project descriptor (protected).
- `Source/ShunyaGame/` - the primary game module. `Public/` for headers, `Private/` for sources, `Private/Tests/` for automation tests. The export macro is `SHUNYAGAME_API`.
- `Source/ShunyaGame/ShunyaGame.Build.cs` - module dependencies (protected; read it to see what you can include).
- `Plugins/ShunyaAgentBridge/` - the studio's editor bridge plugin. Not part of the game; leave it alone unless a task is about it.
- `Docs/` - project documentation you may add to.

## What this project can and cannot use

- The module depends on `Core`, `CoreUObject`, `Engine`, `InputCore`, `EnhancedInput` and `NetCore` only, and `ShunyaGame.Build.cs` is protected. So: no `AIModule` (no `AAIController`, behaviour trees or `MoveTo`), no `NavigationSystem` (no nav mesh), no `UMG` or `Slate`. Enemies steer directly toward their target in `Tick`. The HUD is an `AHUD` subclass that draws with `Canvas` (`DrawText`, `DrawRect`).
- Everything is C++. There are no Blueprints, no input assets and no imported meshes or animations. Bind keys in C++ (`InputComponent->BindAxisKey` / `BindKey` with `EKeys`). Characters and props are built in their constructors from the engine's basic shapes (`/Engine/BasicShapes/Cube`, `Sphere`, `Cylinder`, `Cone`, `Plane`), tinted with the project's materials where they exist.
- Content (materials, textures, sounds, levels, sequences) is created by the art, audio and environment departments with the content tools and lives under `/Game/Shunya/<Folder>/<Name>`, for example `/Game/Shunya/Maps/L_Arena`. Code that loads content by path must tolerate it being absent (fall back to the basic-shape default) because code is merged before content exists.
- A level names its game mode and places game classes by class path (`/Script/ShunyaGame.<ClassName>` without the `A`/`U` prefix), so gameplay actors must work when simply placed in a level or spawned by the game mode.

## The QA autoplay bot contract

Playtests and the packaged-build smoke run start the real game on a map with `-ShunyaAutoPlay` on the command line. When that flag is present the game must play itself and report:

- A `UTickableWorldSubsystem` (created only when `FParse::Param(FCommandLine::Get(), TEXT("ShunyaAutoPlay"))` is true, game worlds only) drives the player through the same input path a human uses.
- A few seconds in, it requests one screenshot: `FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Playtest.png"), true, false)`.
- When the match ends (or after a give-up limit of at most 150 seconds) it logs exactly one line and then quits with `FPlatformMisc::RequestExit(false)` a couple of seconds later:
  `ShunyaPlaytest: {"result":"WIN","score":12,"health":80,"seconds":41.5,"avg_fps":58.2,"worst_frame_ms":40.1,"missing_content":0}`
  `result` is `WIN`, `LOSE` or `TIMEOUT`; `avg_fps` and `worst_frame_ms` are measured over the match; `missing_content` counts content the game loads by path that failed to load. Use `UE_LOG` at `Display` level or higher.
- The bot should be able to win: QA expects `WIN`, an average of at least 20 FPS, and the screenshot.

Automation tests are registered under the `ShunyaGame.` path prefix, e.g. `ShunyaGame.Health.DefaultsToMax`. `Source/ShunyaGame/Private/Tests/ShunyaSmokeTest.cpp` is the reference for how tests are declared in this engine version (flags, includes, guards) - follow its style. Tests run headless (`-nullrhi`), so they must not depend on rendering or on a loaded map; create objects with `NewObject` in the transient package.
