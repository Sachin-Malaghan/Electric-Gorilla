# Project: ShunyaGame

ShunyaGame is the Unreal Engine 5 C++ game the studio is building. Layout, relative to the project root:

- `ShunyaGame.uproject` - project descriptor (protected).
- `Source/ShunyaGame/` - the primary game module. `Public/` for headers, `Private/` for sources, `Private/Tests/` for automation tests. The export macro is `SHUNYAGAME_API`.
- `Source/ShunyaGame/ShunyaGame.Build.cs` - module dependencies (protected; read it to see what you can include).
- `Plugins/ShunyaAgentBridge/` - the studio's editor bridge plugin. Not part of the game; leave it alone unless a task is about it.
- `Docs/` - project documentation you may add to.

Automation tests are registered under the `ShunyaGame.` path prefix, e.g. `ShunyaGame.Health.DefaultsToMax`. `Source/ShunyaGame/Private/Tests/ShunyaSmokeTest.cpp` is the reference for how tests are declared in this engine version (flags, includes, guards) - follow its style. Tests run headless (`-nullrhi`), so they must not depend on rendering or on a loaded map; create objects with `NewObject` in the transient package.
