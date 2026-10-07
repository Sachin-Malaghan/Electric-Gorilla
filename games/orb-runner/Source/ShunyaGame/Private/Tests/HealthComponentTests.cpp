// Automation tests for UHealthComponent - one per acceptance criterion.

#include "Components/HealthComponent.h"
#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace HealthTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;

	UHealthComponent* MakeComponent()
	{
		return NewObject<UHealthComponent>(GetTransientPackage());
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDefaultsTest, "ShunyaGame.Health.DefaultsTo100", HealthTests::Flags)
bool FHealthDefaultsTest::RunTest(const FString& Parameters)
{
	const UHealthComponent* Health = HealthTests::MakeComponent();
	TestEqual(TEXT("Health defaults to 100"), Health->GetHealth(), 100.f);
	TestEqual(TEXT("MaxHealth defaults to 100"), Health->GetMaxHealth(), 100.f);
	TestFalse(TEXT("A new component is alive"), Health->IsDead());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDamageClampTest, "ShunyaGame.Health.DamageCannotGoBelowZero", HealthTests::Flags)
bool FHealthDamageClampTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	TestEqual(TEXT("30 damage is applied in full"), Health->ApplyDamage(30.f), 30.f);
	TestEqual(TEXT("Health is 70 after 30 damage"), Health->GetHealth(), 70.f);
	TestEqual(TEXT("Negative damage is ignored"), Health->ApplyDamage(-50.f), 0.f);
	TestEqual(TEXT("Health unchanged by negative damage"), Health->GetHealth(), 70.f);
	TestEqual(TEXT("Overkill damage only applies what is left"), Health->ApplyDamage(500.f), 70.f);
	TestEqual(TEXT("Health never goes below 0"), Health->GetHealth(), 0.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDeathOnceTest, "ShunyaGame.Health.DeathEventFiresOnce", HealthTests::Flags)
bool FHealthDeathOnceTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	int32 DeathEvents = 0;
	Health->OnDeathNative.AddLambda([&DeathEvents](UHealthComponent*) { ++DeathEvents; });
	Health->ApplyDamage(60.f);
	TestEqual(TEXT("No death event while alive"), DeathEvents, 0);
	Health->ApplyDamage(60.f);
	TestTrue(TEXT("Component is dead at zero health"), Health->IsDead());
	TestEqual(TEXT("Death event fired"), DeathEvents, 1);
	Health->ApplyDamage(10.f);
	Health->ApplyDamage(10.f);
	TestEqual(TEXT("Death event does not fire again"), DeathEvents, 1);
	TestEqual(TEXT("Healing a dead component does nothing"), Health->Heal(50.f), 0.f);
	TestEqual(TEXT("Death event still fired exactly once"), DeathEvents, 1);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthHealClampTest, "ShunyaGame.Health.HealClampsToMax", HealthTests::Flags)
bool FHealthHealClampTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	Health->ApplyDamage(40.f);
	TestEqual(TEXT("Heal restores only up to max"), Health->Heal(100.f), 40.f);
	TestEqual(TEXT("Health is capped at MaxHealth"), Health->GetHealth(), Health->GetMaxHealth());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthReplicationTest, "ShunyaGame.Health.ReplicatedForMultiplayer", HealthTests::Flags)
bool FHealthReplicationTest::RunTest(const FString& Parameters)
{
	const UHealthComponent* Health = HealthTests::MakeComponent();
	TestTrue(TEXT("Component replicates by default"), Health->GetIsReplicated());
	const FProperty* HealthProperty = FindFProperty<FProperty>(UHealthComponent::StaticClass(), TEXT("Health"));
	const FProperty* DeadProperty = FindFProperty<FProperty>(UHealthComponent::StaticClass(), TEXT("bIsDead"));
	TestTrue(TEXT("Health is a replicated property"), HealthProperty && HealthProperty->HasAnyPropertyFlags(CPF_Net));
	TestTrue(TEXT("Health has a RepNotify"), HealthProperty && HealthProperty->HasAnyPropertyFlags(CPF_RepNotify));
	TestTrue(TEXT("bIsDead is a replicated property"), DeadProperty && DeadProperty->HasAnyPropertyFlags(CPF_Net));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
