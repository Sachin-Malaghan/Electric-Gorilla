// Automation tests for player movement maths and the orb defaults.

#include "CoreMinimal.h"
#include "Game/OrbGameMode.h"
#include "Misc/AutomationTest.h"
#include "Pickups/OrbCollectible.h"
#include "Player/OrbRunnerPawn.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace OrbPlayerTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbPlayerMoveDeltaTest, "ShunyaGame.Player.DiagonalMovementIsNotFaster", OrbPlayerTests::Flags)
bool FOrbPlayerMoveDeltaTest::RunTest(const FString& Parameters)
{
	const FVector Forward = AOrbRunnerPawn::ComputeMoveDelta(FVector2D(1.f, 0.f), 700.f, 1.f);
	TestEqual(TEXT("Forward moves along +X at full speed"), Forward, FVector(700.f, 0.f, 0.f));
	const FVector Diagonal = AOrbRunnerPawn::ComputeMoveDelta(FVector2D(1.f, 1.f), 700.f, 1.f);
	TestEqual(TEXT("Diagonal speed equals straight speed"), static_cast<float>(Diagonal.Size()), 700.f, 0.01f);
	TestEqual(TEXT("Movement stays on the ground plane"), static_cast<float>(Diagonal.Z), 0.f);
	TestTrue(TEXT("No input, no movement"), AOrbRunnerPawn::ComputeMoveDelta(FVector2D::ZeroVector, 700.f, 1.f).IsZero());
	TestEqual(TEXT("Half input is half speed"), static_cast<float>(AOrbRunnerPawn::ComputeMoveDelta(FVector2D(0.5f, 0.f), 700.f, 1.f).X), 350.f, 0.01f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbPlayerClampTest, "ShunyaGame.Player.StaysInsideTheArena", OrbPlayerTests::Flags)
bool FOrbPlayerClampTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("Outside is pulled back to the edge"), AOrbRunnerPawn::ClampToArena(FVector(5000.f, -5000.f, 60.f), 1850.f), FVector(1850.f, -1850.f, 60.f));
	TestEqual(TEXT("Inside is untouched"), AOrbRunnerPawn::ClampToArena(FVector(10.f, 20.f, 60.f), 1850.f), FVector(10.f, 20.f, 60.f));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbCollectibleDefaultsTest, "ShunyaGame.Orb.DefaultsMatchTuning", OrbPlayerTests::Flags)
bool FOrbCollectibleDefaultsTest::RunTest(const FString& Parameters)
{
	const AOrbCollectible* Orb = GetDefault<AOrbCollectible>();
	TestEqual(TEXT("An orb is worth 10 points"), Orb->Value, 10);
	TestNotNull(TEXT("Orbs carry the spin/bob idle animation"), Orb->GetSpinBob());
	const AOrbGameMode* GameMode = GetDefault<AOrbGameMode>();
	TestTrue(TEXT("The game mode spawns the runner pawn"), GameMode->DefaultPawnClass == AOrbRunnerPawn::StaticClass());
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
