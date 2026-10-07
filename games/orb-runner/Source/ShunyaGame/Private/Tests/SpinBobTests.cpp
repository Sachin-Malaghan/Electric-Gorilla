// Automation tests for the pickup idle animation maths.

#include "Animation/SpinBobComponent.h"
#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace SpinBobTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSpinBobOffsetTest, "ShunyaGame.Animation.BobIsASineWave", SpinBobTests::Flags)
bool FSpinBobOffsetTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("No offset at time zero"), USpinBobComponent::ComputeBobOffset(0.f, 18.f, 0.5f), 0.f, 0.001f);
	TestEqual(TEXT("Peak a quarter cycle in"), USpinBobComponent::ComputeBobOffset(0.5f, 18.f, 0.5f), 18.f, 0.001f);
	TestEqual(TEXT("Back to rest after half a cycle"), USpinBobComponent::ComputeBobOffset(1.f, 18.f, 0.5f), 0.f, 0.001f);
	TestEqual(TEXT("Trough three quarters in"), USpinBobComponent::ComputeBobOffset(1.5f, 18.f, 0.5f), -18.f, 0.001f);
	TestEqual(TEXT("Zero amplitude never moves"), USpinBobComponent::ComputeBobOffset(0.37f, 0.f, 2.f), 0.f, 0.001f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSpinBobYawTest, "ShunyaGame.Animation.YawWrapsAt360", SpinBobTests::Flags)
bool FSpinBobYawTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("90 degrees per second for one second"), USpinBobComponent::ComputeYaw(1.f, 90.f), 90.f, 0.001f);
	TestEqual(TEXT("Wraps past a full turn"), USpinBobComponent::ComputeYaw(5.f, 90.f), 90.f, 0.001f);
	TestEqual(TEXT("Negative spin stays in range"), USpinBobComponent::ComputeYaw(1.f, -90.f), 270.f, 0.001f);
	const float Yaw = USpinBobComponent::ComputeYaw(1234.5f, 77.f);
	TestTrue(TEXT("Always within [0, 360)"), Yaw >= 0.f && Yaw < 360.f);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
