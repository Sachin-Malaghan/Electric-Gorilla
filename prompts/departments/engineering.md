# Engineering department

The codebase is an Unreal Engine 5 C++ project. Engineering standards:

- Follow Epic's conventions: `A` Actors, `U` UObjects/components, `F` structs, `E` enums, `I` interfaces; `UCLASS`/`UPROPERTY`/`UFUNCTION` so the editor, Blueprints and GC can see what they need to.
- Headers go in the module's `Public/` folder (or `Private/` if not part of the module API) and include the matching `.generated.h` last; the class is exported with the module's `_API` macro.
- Gameplay state that matters in multiplayer is replicated: `SetIsReplicatedByDefault(true)`, `UPROPERTY(ReplicatedUsing=...)`, `GetLifetimeReplicatedProps`, and state changes only on the authority.
- Every behaviour in the acceptance criteria gets an Unreal Automation Framework test (`IMPLEMENT_SIMPLE_AUTOMATION_TEST`) under the task's test path prefix, in the module's `Private/Tests/` folder, guarded with `#if WITH_DEV_AUTOMATION_TESTS`. Tests must assert the behaviour, not merely run.
- Module dependencies (`*.Build.cs`), `*.Target.cs`, the `.uproject` and `Config/` are protected. If a task truly needs a change there, report it rather than attempting it.
- Compiling takes minutes. Make a complete change, then compile; do not compile after every small edit.
