// Automation tests for the QA bot's decisions.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Tools/OrbPlaytestSubsystem.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace OrbPlaytestTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlaytestPickNearestTest, "ShunyaGame.Tools.BotPicksTheNearestOrb", OrbPlaytestTests::Flags)
bool FPlaytestPickNearestTest::RunTest(const FString& Parameters)
{
	const TArray<FVector> Orbs = {FVector(900.f, 0.f, 80.f), FVector(-200.f, 100.f, 80.f), FVector(0.f, 1500.f, 80.f)};
	TestEqual(TEXT("Nearest of three"), UOrbPlaytestSubsystem::PickNearest(FVector::ZeroVector, Orbs), 1);
	TestEqual(TEXT("Height is ignored"), UOrbPlaytestSubsystem::PickNearest(FVector(850.f, 0.f, 5000.f), Orbs), 0);
	TestEqual(TEXT("No orbs left"), UOrbPlaytestSubsystem::PickNearest(FVector::ZeroVector, TArray<FVector>()), static_cast<int32>(INDEX_NONE));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlaytestBotInputTest, "ShunyaGame.Tools.BotSteersToOrbsAndAwayFromTheDrone", OrbPlaytestTests::Flags)
bool FPlaytestBotInputTest::RunTest(const FString& Parameters)
{
	const FVector2D Clear = UOrbPlaytestSubsystem::ComputeBotInput(FVector::ZeroVector, FVector(500.f, 0.f, 0.f), FVector(0.f, 5000.f, 0.f), 420.f);
	TestEqual(TEXT("Heads straight for the orb when the drone is far"), Clear, FVector2D(1.0, 0.0));
	const FVector2D Dodging = UOrbPlaytestSubsystem::ComputeBotInput(FVector::ZeroVector, FVector(500.f, 0.f, 0.f), FVector(0.f, 100.f, 0.f), 420.f);
	TestTrue(TEXT("Still makes progress toward the orb"), Dodging.X > 0.0);
	TestTrue(TEXT("Leans away from a nearby drone"), Dodging.Y < -0.1);
	TestEqual(TEXT("Input is unit length"), static_cast<float>(Dodging.Size()), 1.f, 0.001f);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
