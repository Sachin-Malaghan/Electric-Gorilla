// Automation tests for the drone pursuit maths.

#include "AI/ChaserDrone.h"
#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Player/OrbRunnerPawn.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ChaserDroneTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDroneSteerTest, "ShunyaGame.AI.DroneMovesTowardThePlayer", ChaserDroneTests::Flags)
bool FDroneSteerTest::RunTest(const FString& Parameters)
{
	const FVector Step = AChaserDrone::ComputeSteer(FVector(0.f, 0.f, 80.f), FVector(1000.f, 0.f, 60.f), 260.f, 1.f);
	TestEqual(TEXT("Moves at its speed toward the target"), Step, FVector(260.f, 0.f, 0.f));
	const FVector Diagonal = AChaserDrone::ComputeSteer(FVector::ZeroVector, FVector(300.f, 400.f, 0.f), 100.f, 1.f);
	TestEqual(TEXT("Heads straight for the target"), Diagonal, FVector(60.f, 80.f, 0.f));
	TestEqual(TEXT("Stays at its own height"), static_cast<float>(Step.Z), 0.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDroneNoOvershootTest, "ShunyaGame.AI.DroneNeverOvershoots", ChaserDroneTests::Flags)
bool FDroneNoOvershootTest::RunTest(const FString& Parameters)
{
	const FVector Step = AChaserDrone::ComputeSteer(FVector::ZeroVector, FVector(50.f, 0.f, 0.f), 260.f, 1.f);
	TestEqual(TEXT("Stops on the target instead of passing it"), Step, FVector(50.f, 0.f, 0.f));
	TestTrue(TEXT("Does not move when already there"), AChaserDrone::ComputeSteer(FVector(5.f, 5.f, 0.f), FVector(5.f, 5.f, 90.f), 260.f, 1.f).IsZero());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDroneTuningTest, "ShunyaGame.AI.DroneIsSlowerThanThePlayerAndHitsOnCooldown", ChaserDroneTests::Flags)
bool FDroneTuningTest::RunTest(const FString& Parameters)
{
	const AChaserDrone* Drone = GetDefault<AChaserDrone>();
	const AOrbRunnerPawn* Player = GetDefault<AOrbRunnerPawn>();
	TestTrue(TEXT("The player can always outrun the drone"), Drone->Speed < Player->MoveSpeed);
	TestEqual(TEXT("Contact damage is a quarter of full health"), Drone->ContactDamage, 25.f);
	TestFalse(TEXT("Cannot hit again inside the cooldown"), AChaserDrone::CanDamage(0.4f, Drone->DamageCooldown));
	TestTrue(TEXT("Can hit once the cooldown has passed"), AChaserDrone::CanDamage(1.f, Drone->DamageCooldown));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
