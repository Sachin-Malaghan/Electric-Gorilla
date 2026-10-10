// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Characters/EnemyCharacter.h"
#include "Components/HealthComponent.h"
#include "Engine/DamageEvents.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaEnemyTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// AC 1: Defaults (50 Health, 320 speed, 120 attack range, 15 attack damage, 1.5s attack cooldown)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnemyCharacterDefaultsTest, "ShunyaGame.Enemy.Defaults", ShunyaEnemyTests::Flags)
bool FEnemyCharacterDefaultsTest::RunTest(const FString& Parameters)
{
	AEnemyCharacter* Enemy = NewObject<AEnemyCharacter>();
	TestNotNull(TEXT("EnemyCharacter should be created"), Enemy);
	if (!Enemy)
	{
		return false;
	}

	UHealthComponent* HealthComp = Enemy->GetHealthComponent();
	TestNotNull(TEXT("Enemy has HealthComponent"), HealthComp);
	if (HealthComp)
	{
		TestEqual(TEXT("Enemy default MaxHealth is 50"), HealthComp->GetMaxHealth(), 50.0f);
		TestEqual(TEXT("Enemy default CurrentHealth is 50"), HealthComp->GetHealth(), 50.0f);
	}

	TestEqual(TEXT("Default MovementSpeed is 320.0"), Enemy->GetMovementSpeed(), 320.0f);
	TestEqual(TEXT("Default AttackRange is 120.0"), Enemy->GetAttackRange(), 120.0f);
	TestEqual(TEXT("Default AttackDamage is 15.0"), Enemy->GetAttackDamage(), 15.0f);
	TestEqual(TEXT("Default AttackCooldown is 1.5"), Enemy->GetAttackCooldown(), 1.5f);
	TestEqual(TEXT("Default AttackCooldownTimer is 0.0"), Enemy->GetAttackCooldownTimer(), 0.0f);
	TestFalse(TEXT("Enemy starts alive"), Enemy->IsDead());

	return true;
}

// AC 2: Steering directly toward player on XY plane at 320 units/s
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnemyCharacterSteeringCalculationTest, "ShunyaGame.Enemy.SteeringCalculation", ShunyaEnemyTests::Flags)
bool FEnemyCharacterSteeringCalculationTest::RunTest(const FString& Parameters)
{
	const FVector CurrentPos(100.0f, 200.0f, 50.0f);
	const FVector TargetPos(400.0f, 600.0f, 150.0f); // dx=300, dy=400, lengthXY = 500
	const float Speed = 320.0f;

	FVector Velocity = AEnemyCharacter::CalculateSteeringVelocity(CurrentPos, TargetPos, Speed);

	// Z velocity must be 0 (XY planar)
	TestNearlyEqual(TEXT("Steering Z velocity is 0"), static_cast<float>(Velocity.Z), 0.0f, 0.001f);

	// Velocity 2D magnitude must equal Speed (320 units/s)
	TestNearlyEqual(TEXT("Steering speed equals 320"), static_cast<float>(Velocity.Size2D()), 320.0f, 0.001f);

	// Direction unit vector should be (300/500, 400/500, 0) = (0.6, 0.8, 0)
	// So Velocity = (192, 256, 0)
	TestNearlyEqual(TEXT("Steering X velocity"), static_cast<float>(Velocity.X), 192.0f, 0.1f);
	TestNearlyEqual(TEXT("Steering Y velocity"), static_cast<float>(Velocity.Y), 256.0f, 0.1f);

	// Zero distance target check
	FVector SamePosVel = AEnemyCharacter::CalculateSteeringVelocity(CurrentPos, CurrentPos, Speed);
	TestEqual(TEXT("Steering velocity is zero when at target position"), SamePosVel, FVector::ZeroVector);

	return true;
}

// AC 3: Close-range attack execution, damage dealing to player, and cooldown cadence
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnemyCharacterAttackAndCooldownTest, "ShunyaGame.Enemy.AttackCadenceAndCooldown", ShunyaEnemyTests::Flags)
bool FEnemyCharacterAttackAndCooldownTest::RunTest(const FString& Parameters)
{
	AEnemyCharacter* Enemy = NewObject<AEnemyCharacter>();
	TestNotNull(TEXT("Enemy created"), Enemy);
	if (!Enemy)
	{
		return false;
	}

	// Create a dummy target actor equipped with a HealthComponent
	AActor* TargetDummy = NewObject<AActor>();
	UHealthComponent* TargetHealth = NewObject<UHealthComponent>(TargetDummy);
	TargetHealth->SetMaxHealth(100.0f, true);

	// Set enemy position
	Enemy->SetActorLocation(FVector(0.0f, 0.0f, 0.0f));
	const FVector TargetLocation(100.0f, 0.0f, 0.0f); // 100 units away (< 120 AttackRange)

	// Update logic: enemy should attack target actor (executes attack -> timer set to 1.5)
	Enemy->UpdateEnemyLogic(0.1f, TargetLocation, TargetDummy);

	TestEqual(TEXT("Target took 15 damage (health is 85)"), TargetHealth->GetHealth(), 85.0f);
	TestNearlyEqual(TEXT("AttackCooldownTimer set to 1.5"), Enemy->GetAttackCooldownTimer(), 1.5f, 0.01f);

	// Another update before cooldown expires: no new attack should occur, cooldown ticks down by 0.5s to 1.0s
	Enemy->UpdateEnemyLogic(0.5f, TargetLocation, TargetDummy);
	TestEqual(TEXT("Target took no extra damage while cooldown is active"), TargetHealth->GetHealth(), 85.0f);
	TestNearlyEqual(TEXT("AttackCooldownTimer decreased to 1.0s"), Enemy->GetAttackCooldownTimer(), 1.0f, 0.01f);

	// Advance past remaining cooldown (1.0s)
	Enemy->UpdateEnemyLogic(1.0f, TargetLocation, TargetDummy);
	// In this update, timer reaches 0, so another attack executes (15 damage dealt, timer resets to 1.5)
	TestEqual(TEXT("Target took second attack (health is 70)"), TargetHealth->GetHealth(), 70.0f);
	TestNearlyEqual(TEXT("AttackCooldownTimer reset to 1.5s"), Enemy->GetAttackCooldownTimer(), 1.5f, 0.01f);

	return true;
}

// AC 3: Damage reception and death triggering when reaching 0 health
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEnemyCharacterDamageIntakeAndDeathTest, "ShunyaGame.Enemy.DamageIntakeAndDeath", ShunyaEnemyTests::Flags)
bool FEnemyCharacterDamageIntakeAndDeathTest::RunTest(const FString& Parameters)
{
	AEnemyCharacter* Enemy = NewObject<AEnemyCharacter>();
	TestNotNull(TEXT("Enemy created"), Enemy);
	if (!Enemy)
	{
		return false;
	}

	UHealthComponent* HealthComp = Enemy->GetHealthComponent();
	TestNotNull(TEXT("Enemy has HealthComponent"), HealthComp);
	if (!HealthComp)
	{
		return false;
	}

	TestEqual(TEXT("Initial health is 50"), HealthComp->GetHealth(), 50.0f);
	TestFalse(TEXT("Initially not dead"), Enemy->IsDead());

	// Receive non-lethal damage via TakeDamage
	FDamageEvent DamageEvent;
	Enemy->TakeDamage(20.0f, DamageEvent, nullptr, nullptr);

	TestEqual(TEXT("Health reduced to 30"), HealthComp->GetHealth(), 30.0f);
	TestFalse(TEXT("Still alive after 20 damage"), Enemy->IsDead());

	// Receive lethal damage
	Enemy->TakeDamage(30.0f, DamageEvent, nullptr, nullptr);

	TestEqual(TEXT("Health reduced to 0"), HealthComp->GetHealth(), 0.0f);
	TestTrue(TEXT("Enemy IsDead flag set on 0 health"), Enemy->IsDead());
	TestTrue(TEXT("HealthComponent reports dead"), HealthComp->IsDead());

	// Damage intake after death is ignored
	Enemy->TakeDamage(10.0f, DamageEvent, nullptr, nullptr);
	TestEqual(TEXT("Health stays 0"), HealthComp->GetHealth(), 0.0f);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
