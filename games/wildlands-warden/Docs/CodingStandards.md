# ShunyaGame coding standards

## Naming
Epic's conventions: `A` Actors, `U` UObjects and components, `F` structs, `E` enums, `I` interfaces. Booleans start with `b`.

## Module layout
- `Source/ShunyaGame/Public/` - headers that are part of the module API. Group by feature folder (`Components/`, `Characters/`, ...).
- `Source/ShunyaGame/Private/` - sources and private headers, mirroring the `Public/` folders.
- `Source/ShunyaGame/Private/Tests/` - automation tests, one file per feature, `ShunyaGame.<Feature>.<Behaviour>` paths.

## Components
Reusable gameplay state lives in `UActorComponent` subclasses, not in character classes. A component exposes:
- `BlueprintReadOnly` state with `BlueprintPure` getters,
- `BlueprintCallable` mutators that validate their input,
- `BlueprintAssignable` multicast delegates for state changes.

## Multiplayer
Gameplay state is server-authoritative. Components that hold gameplay state call `SetIsReplicatedByDefault(true)`, replicate their state with `ReplicatedUsing` notifies, and only mutate it when the owner has authority (or has no owner, as in unit tests).

## Tests
Every acceptance criterion has an automation test. Tests construct objects with `NewObject<>()` in the transient package and assert behaviour with `TestEqual` / `TestTrue`. A test that cannot fail is not a test.
