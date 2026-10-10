// Copyright Shunya Studios. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Components/StaminaComponent.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// 1. Defaults and Initialization
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaDefaultsTest, "ShunyaGame.Stamina.DefaultsToMax", ShunyaTests::Flags)
bool FStaminaDefaultsTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	TestEqual(TEXT("MaxStamina defaults to 100.0f"), StaminaComp->GetMaxStamina(), 100.0f);
	TestEqual(TEXT("CurrentStamina initializes to MaxStamina (100.0f)"), StaminaComp->GetCurrentStamina(), 100.0f);
	TestTrue(TEXT("Component is replicated by default"), StaminaComp->GetIsReplicated());

	return true;
}

// 2. Consumption and Clamping
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaConsumptionTest, "ShunyaGame.Stamina.ConsumptionAndClamping", ShunyaTests::Flags)
bool FStaminaConsumptionTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	// Normal consumption
	StaminaComp->ConsumeStamina(30.0f);
	TestEqual(TEXT("Consuming 30 stamina leaves 70"), StaminaComp->GetCurrentStamina(), 70.0f);

	// Over-consumption clamps to 0
	StaminaComp->ConsumeStamina(100.0f);
	TestEqual(TEXT("Over-consumption clamps CurrentStamina to 0.0f"), StaminaComp->GetCurrentStamina(), 0.0f);

	return true;
}

// 3. Invalid / Non-positive Input
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaInvalidInputTest, "ShunyaGame.Stamina.InvalidInputHandling", ShunyaTests::Flags)
bool FStaminaInvalidInputTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	StaminaComp->ConsumeStamina(0.0f);
	TestEqual(TEXT("Consuming 0 stamina does nothing"), StaminaComp->GetCurrentStamina(), 100.0f);

	StaminaComp->ConsumeStamina(-25.0f);
	TestEqual(TEXT("Consuming negative stamina does nothing"), StaminaComp->GetCurrentStamina(), 100.0f);

	return true;
}

// 4. Single-fire Depletion Event
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaDepletionEventTest, "ShunyaGame.Stamina.SingleFireDepletionEvent", ShunyaTests::Flags)
bool FStaminaDepletionEventTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	int32 DynamicDepleteCount = 0;
	int32 NativeDepleteCount = 0;

	StaminaComp->OnStaminaDepletedNative.AddLambda([&NativeDepleteCount]()
	{
		NativeDepleteCount++;
	});

	// Consume partially
	StaminaComp->ConsumeStamina(50.0f);
	TestEqual(TEXT("No depletion fired on partial consume"), NativeDepleteCount, 0);

	// Consume to 0 -> should fire once
	StaminaComp->ConsumeStamina(50.0f);
	TestEqual(TEXT("CurrentStamina is 0"), StaminaComp->GetCurrentStamina(), 0.0f);
	TestEqual(TEXT("Depletion event fired exactly once when reaching 0"), NativeDepleteCount, 1);

	// Subsequent consumption while at 0 -> should not re-fire
	StaminaComp->ConsumeStamina(20.0f);
	TestEqual(TEXT("Depletion event did not re-fire while at 0"), NativeDepleteCount, 1);

	return true;
}

// 5. Delayed Regeneration and Clamping
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaDelayedRegenTest, "ShunyaGame.Stamina.DelayedRegeneration", ShunyaTests::Flags)
bool FStaminaDelayedRegenTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	StaminaComp->SetStaminaRegenDelay(1.0f);
	StaminaComp->SetStaminaRegenRate(20.0f);

	// Consume 50 stamina
	StaminaComp->ConsumeStamina(50.0f);
	TestEqual(TEXT("CurrentStamina is 50"), StaminaComp->GetCurrentStamina(), 50.0f);

	// Tick during delay period (0.5s < 1.0s) -> no regen
	StaminaComp->RegenerateStamina(0.5f);
	TestEqual(TEXT("Stamina does not regenerate during regen delay"), StaminaComp->GetCurrentStamina(), 50.0f);

	// Tick another 0.4s (total 0.9s < 1.0s) -> still no regen
	StaminaComp->RegenerateStamina(0.4f);
	TestEqual(TEXT("Stamina does not regenerate before delay completes"), StaminaComp->GetCurrentStamina(), 50.0f);

	// Tick 0.2s (total 1.1s >= 1.0s) -> regen starts and adds 20 * 0.2 = 4.0
	StaminaComp->RegenerateStamina(0.2f);
	TestEqual(TEXT("Stamina regenerates after delay is met"), StaminaComp->GetCurrentStamina(), 54.0f);

	// Tick 5 seconds -> should cap at MaxStamina (100.0f)
	StaminaComp->RegenerateStamina(5.0f);
	TestEqual(TEXT("Stamina caps at MaxStamina"), StaminaComp->GetCurrentStamina(), 100.0f);

	return true;
}

// 6. Depletion Event Re-arming after Regeneration
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FStaminaDepletionRearmTest, "ShunyaGame.Stamina.DepletionRearmAfterRegen", ShunyaTests::Flags)
bool FStaminaDepletionRearmTest::RunTest(const FString& Parameters)
{
	UStaminaComponent* StaminaComp = NewObject<UStaminaComponent>(GetTransientPackage(), UStaminaComponent::StaticClass());
	TestNotNull(TEXT("StaminaComponent created successfully"), StaminaComp);
	if (!StaminaComp)
	{
		return false;
	}

	int32 NativeDepleteCount = 0;
	StaminaComp->OnStaminaDepletedNative.AddLambda([&NativeDepleteCount]()
	{
		NativeDepleteCount++;
	});

	// Deplete to 0
	StaminaComp->ConsumeStamina(100.0f);
	TestEqual(TEXT("Depletion count is 1"), NativeDepleteCount, 1);

	// Regenerate back above 0
	StaminaComp->SetStaminaRegenDelay(1.0f);
	StaminaComp->SetStaminaRegenRate(20.0f);
	StaminaComp->RegenerateStamina(1.5f);
	TestTrue(TEXT("Stamina restored above 0"), StaminaComp->GetCurrentStamina() > 0.0f);

	// Deplete to 0 again -> should fire second time
	StaminaComp->ConsumeStamina(StaminaComp->GetCurrentStamina());
	TestEqual(TEXT("Depletion count is 2 after re-depleting"), NativeDepleteCount, 2);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
