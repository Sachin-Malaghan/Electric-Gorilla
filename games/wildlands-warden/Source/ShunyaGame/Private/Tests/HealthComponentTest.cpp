// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Components/HealthComponent.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaCombatTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthComponentDefaultsTest, "ShunyaGame.Combat.Health.Defaults", ShunyaCombatTests::Flags)
bool FHealthComponentDefaultsTest::RunTest(const FString& Parameters)
{
	UHealthComponent* HealthComp = NewObject<UHealthComponent>();
	TestNotNull(TEXT("HealthComponent should be created"), HealthComp);
	if (!HealthComp)
	{
		return false;
	}

	TestEqual(TEXT("Default MaxHealth should be 100"), HealthComp->GetMaxHealth(), 100.0f);
	TestEqual(TEXT("Default CurrentHealth should be 100"), HealthComp->GetHealth(), 100.0f);
	TestEqual(TEXT("Default HealthPercent should be 1.0"), HealthComp->GetHealthPercent(), 1.0f);
	TestFalse(TEXT("Default IsDead should be false"), HealthComp->IsDead());

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthComponentDamageAndClampingTest, "ShunyaGame.Combat.Health.DamageAndClamping", ShunyaCombatTests::Flags)
bool FHealthComponentDamageAndClampingTest::RunTest(const FString& Parameters)
{
	UHealthComponent* HealthComp = NewObject<UHealthComponent>();
	TestNotNull(TEXT("HealthComponent should be created"), HealthComp);
	if (!HealthComp)
	{
		return false;
	}

	// Negative or zero damage should be ignored
	TestFalse(TEXT("Negative damage rejected"), HealthComp->ApplyDamage(-10.0f));
	TestFalse(TEXT("Zero damage rejected"), HealthComp->ApplyDamage(0.0f));
	TestEqual(TEXT("Health unchanged after invalid damage"), HealthComp->GetHealth(), 100.0f);

	// Normal damage
	TestTrue(TEXT("Valid damage applied"), HealthComp->ApplyDamage(40.0f));
	TestEqual(TEXT("Health reduced by 40"), HealthComp->GetHealth(), 60.0f);
	TestEqual(TEXT("HealthPercent is 0.6"), HealthComp->GetHealthPercent(), 0.6f);
	TestFalse(TEXT("Not dead yet"), HealthComp->IsDead());

	// Overkill damage should clamp to 0
	TestTrue(TEXT("Overkill damage applied"), HealthComp->ApplyDamage(100.0f));
	TestEqual(TEXT("Health clamped to 0"), HealthComp->GetHealth(), 0.0f);
	TestEqual(TEXT("Health cannot drop below 0"), HealthComp->GetHealthPercent(), 0.0f);
	TestTrue(TEXT("Actor is now dead"), HealthComp->IsDead());

	// Damage after death should be rejected
	TestFalse(TEXT("Damage after death rejected"), HealthComp->ApplyDamage(10.0f));
	TestEqual(TEXT("Health remains 0"), HealthComp->GetHealth(), 0.0f);

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthComponentDeathDelegateFiresOnceTest, "ShunyaGame.Combat.Health.DeathDelegateFiresOnce", ShunyaCombatTests::Flags)
bool FHealthComponentDeathDelegateFiresOnceTest::RunTest(const FString& Parameters)
{
	UHealthComponent* HealthComp = NewObject<UHealthComponent>();
	TestNotNull(TEXT("HealthComponent should be created"), HealthComp);
	if (!HealthComp)
	{
		return false;
	}

	int32 DeathCallCount = 0;
	HealthComp->OnDeathNative.AddLambda([&DeathCallCount](AActor* DeadActor)
	{
		DeathCallCount++;
	});

	// Partial damage: no death delegate
	HealthComp->ApplyDamage(50.0f);
	TestEqual(TEXT("Death delegate not fired on partial damage"), DeathCallCount, 0);

	// Fatal damage: death delegate fires exactly once
	HealthComp->ApplyDamage(60.0f);
	TestEqual(TEXT("Health at 0"), HealthComp->GetHealth(), 0.0f);
	TestEqual(TEXT("Death delegate fired once"), DeathCallCount, 1);

	// Further damage attempts should not re-trigger death delegate
	HealthComp->ApplyDamage(50.0f);
	TestEqual(TEXT("Death delegate still only fired once after further damage"), DeathCallCount, 1);

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthComponentHealingTest, "ShunyaGame.Combat.Health.Healing", ShunyaCombatTests::Flags)
bool FHealthComponentHealingTest::RunTest(const FString& Parameters)
{
	UHealthComponent* HealthComp = NewObject<UHealthComponent>();
	TestNotNull(TEXT("HealthComponent should be created"), HealthComp);
	if (!HealthComp)
	{
		return false;
	}

	// Cannot heal when already full
	TestFalse(TEXT("Healing at full health rejected"), HealthComp->Heal(10.0f));

	// Take damage then heal
	HealthComp->ApplyDamage(50.0f);
	TestEqual(TEXT("Health is 50"), HealthComp->GetHealth(), 50.0f);

	TestTrue(TEXT("Healing applied"), HealthComp->Heal(20.0f));
	TestEqual(TEXT("Health is 70"), HealthComp->GetHealth(), 70.0f);

	// Over-healing should clamp to MaxHealth
	TestTrue(TEXT("Overheal applied"), HealthComp->Heal(100.0f));
	TestEqual(TEXT("Health clamped to MaxHealth"), HealthComp->GetHealth(), 100.0f);

	// Negative or zero healing
	TestFalse(TEXT("Zero heal rejected"), HealthComp->Heal(0.0f));
	TestFalse(TEXT("Negative heal rejected"), HealthComp->Heal(-10.0f));

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
