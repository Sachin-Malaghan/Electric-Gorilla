// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "CombatAutoPlaySubsystem.h"
#include "Characters/EnemyCharacter.h"
#include "Components/HealthComponent.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaAutoPlayTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// 1. Acceptance Criterion 1 & 5: Subsystem class registration and reflection
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlaySubsystemRegistrationTest, "ShunyaGame.AutoPlay.Registration", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlaySubsystemRegistrationTest::RunTest(const FString& Parameters)
{
	const UClass* SubsystemClass = UCombatAutoPlaySubsystem::StaticClass();
	TestNotNull(TEXT("UCombatAutoPlaySubsystem is registered with reflection system"), SubsystemClass);
	TestTrue(TEXT("UCombatAutoPlaySubsystem derives from UTickableWorldSubsystem"), SubsystemClass && SubsystemClass->IsChildOf(UTickableWorldSubsystem::StaticClass()));

	// Verify world type support
	UCombatAutoPlaySubsystem* Subsystem = NewObject<UCombatAutoPlaySubsystem>();
	TestNotNull(TEXT("Subsystem can be instantiated"), Subsystem);
	if (Subsystem)
	{
		TestTrue(TEXT("Supports Game world"), Subsystem->DoesSupportWorldType(EWorldType::Game));
		TestTrue(TEXT("Supports PIE world"), Subsystem->DoesSupportWorldType(EWorldType::PIE));
		TestFalse(TEXT("Does not support Editor world"), Subsystem->DoesSupportWorldType(EWorldType::Editor));
		TestFalse(TEXT("Does not support Inactive world"), Subsystem->DoesSupportWorldType(EWorldType::Inactive));
	}

	return true;
}

// 2. Acceptance Criterion 1 & 5: Command line detection logic
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayCommandLineDetectionTest, "ShunyaGame.AutoPlay.CommandLineDetection", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayCommandLineDetectionTest::RunTest(const FString& Parameters)
{
	// Test pure predicate ShouldRunAutoPlay
	TestTrue(TEXT("Runs when command line flag is true and world is Game"),
		UCombatAutoPlaySubsystem::ShouldRunAutoPlay(true, EWorldType::Game));

	TestTrue(TEXT("Runs when command line flag is true and world is PIE"),
		UCombatAutoPlaySubsystem::ShouldRunAutoPlay(true, EWorldType::PIE));

	TestFalse(TEXT("Does not run when command line flag is false in Game world"),
		UCombatAutoPlaySubsystem::ShouldRunAutoPlay(false, EWorldType::Game));

	TestFalse(TEXT("Does not run when command line flag is true in Editor world"),
		UCombatAutoPlaySubsystem::ShouldRunAutoPlay(true, EWorldType::Editor));

	TestFalse(TEXT("Does not run when command line flag is true in None/Inactive world"),
		UCombatAutoPlaySubsystem::ShouldRunAutoPlay(true, EWorldType::None));

	return true;
}

// 3. Acceptance Criterion 2: Steering and rotation calculations
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlaySteeringAndAimTest, "ShunyaGame.AutoPlay.SteeringAndAim", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlaySteeringAndAimTest::RunTest(const FString& Parameters)
{
	const FVector PlayerPos(100.0f, 100.0f, 50.0f);
	const FVector EnemyPos(400.0f, 100.0f, 120.0f); // 300 units directly ahead along +X

	FVector Direction = UCombatAutoPlaySubsystem::CalculateSteeringDirection(PlayerPos, EnemyPos);
	TestNearlyEqual(TEXT("Steering direction X is 1.0"), static_cast<float>(Direction.X), 1.0f, 0.001f);
	TestNearlyEqual(TEXT("Steering direction Y is 0.0"), static_cast<float>(Direction.Y), 0.0f, 0.001f);
	TestNearlyEqual(TEXT("Steering direction Z is 0.0"), static_cast<float>(Direction.Z), 0.0f, 0.001f);

	FRotator Aim = UCombatAutoPlaySubsystem::CalculateAimRotation(PlayerPos, EnemyPos);
	TestNearlyEqual(TEXT("Aim Yaw is 0.0 (facing +X)"), static_cast<float>(Aim.Yaw), 0.0f, 0.1f);
	TestNearlyEqual(TEXT("Aim Pitch is 0.0"), static_cast<float>(Aim.Pitch), 0.0f, 0.1f);
	TestNearlyEqual(TEXT("Aim Roll is 0.0"), static_cast<float>(Aim.Roll), 0.0f, 0.1f);

	// Test 90-degree angle (+Y)
	const FVector EnemyPosY(100.0f, 500.0f, 50.0f);
	FVector DirY = UCombatAutoPlaySubsystem::CalculateSteeringDirection(PlayerPos, EnemyPosY);
	TestNearlyEqual(TEXT("Steering direction Y is 1.0"), static_cast<float>(DirY.Y), 1.0f, 0.001f);
	FRotator AimY = UCombatAutoPlaySubsystem::CalculateAimRotation(PlayerPos, EnemyPosY);
	TestNearlyEqual(TEXT("Aim Yaw is 90.0 (facing +Y)"), static_cast<float>(AimY.Yaw), 90.0f, 0.1f);

	return true;
}

// 4. Acceptance Criterion 3: Screenshot request timing (~3.0s into match)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayScreenshotTimingTest, "ShunyaGame.AutoPlay.ScreenshotTiming", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayScreenshotTimingTest::RunTest(const FString& Parameters)
{
	UCombatAutoPlaySubsystem* Subsystem = NewObject<UCombatAutoPlaySubsystem>();
	TestNotNull(TEXT("Subsystem instantiated"), Subsystem);

	// Before 3.0s, screenshot should not have been requested
	Subsystem->SimulateTick(1.0f);
	TestNearlyEqual(TEXT("Match seconds is 1.0s"), Subsystem->GetMatchSeconds(), 1.0f, 0.001f);
	TestFalse(TEXT("Screenshot not requested at 1.0s"), Subsystem->HasRequestedScreenshot());

	Subsystem->SimulateTick(1.5f);
	TestNearlyEqual(TEXT("Match seconds is 2.5s"), Subsystem->GetMatchSeconds(), 2.5f, 0.001f);
	TestFalse(TEXT("Screenshot not requested at 2.5s"), Subsystem->HasRequestedScreenshot());

	// At >= 3.0s, screenshot should be triggered
	Subsystem->SimulateTick(0.6f);
	TestNearlyEqual(TEXT("Match seconds is 3.1s"), Subsystem->GetMatchSeconds(), 3.1f, 0.001f);
	TestTrue(TEXT("Screenshot requested at >= 3.0s"), Subsystem->HasRequestedScreenshot());

	// Additional ticks should not trigger screenshot again
	Subsystem->SimulateTick(1.0f);
	TestTrue(TEXT("Screenshot still flagged as requested"), Subsystem->HasRequestedScreenshot());

	return true;
}

// 5. Acceptance Criterion 4: Structured test results log formatting
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayOutputFormatTest, "ShunyaGame.AutoPlay.OutputFormat", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayOutputFormatTest::RunTest(const FString& Parameters)
{
	FString Formatted = UCombatAutoPlaySubsystem::FormatPlaytestOutput(
		TEXT("WIN"), 1200, 80, 41.5f, 58.2f, 40.1f, 0
	);

	const FString Expected = TEXT("ShunyaPlaytest: {\"result\":\"WIN\",\"score\":1200,\"health\":80,\"seconds\":41.5,\"avg_fps\":58.2,\"worst_frame_ms\":40.1,\"missing_content\":0}");
	TestEqual(TEXT("Formatted output matches expected QA schema"), Formatted, Expected);

	// Test TIMEOUT formatting
	FString TimeoutOutput = UCombatAutoPlaySubsystem::FormatPlaytestOutput(
		TEXT("TIMEOUT"), 300, 100, 150.0f, 60.0f, 16.6f, 0
	);
	const FString ExpectedTimeout = TEXT("ShunyaPlaytest: {\"result\":\"TIMEOUT\",\"score\":300,\"health\":100,\"seconds\":150.0,\"avg_fps\":60.0,\"worst_frame_ms\":16.6,\"missing_content\":0}");
	TestEqual(TEXT("Timeout output matches expected schema"), TimeoutOutput, ExpectedTimeout);

	return true;
}

// 6. Acceptance Criterion 4: Timeout handling at 150s
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayTimeoutTest, "ShunyaGame.AutoPlay.TimeoutAt150s", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayTimeoutTest::RunTest(const FString& Parameters)
{
	UCombatAutoPlaySubsystem* Subsystem = NewObject<UCombatAutoPlaySubsystem>();
	TestNotNull(TEXT("Subsystem instantiated"), Subsystem);

	// Simulate up to 149 seconds
	Subsystem->SimulateTick(149.0f);
	TestFalse(TEXT("Test not completed before 150s"), Subsystem->HasCompletedTest());

	// Tick across 150 seconds threshold
	Subsystem->SimulateTick(1.5f);
	TestTrue(TEXT("Test marked completed upon reaching 150s"), Subsystem->HasCompletedTest());

	return true;
}

// 7. Telemetry tracking (Average FPS and Worst Frame MS)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayTelemetryTest, "ShunyaGame.AutoPlay.TelemetryMetrics", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayTelemetryTest::RunTest(const FString& Parameters)
{
	UCombatAutoPlaySubsystem* Subsystem = NewObject<UCombatAutoPlaySubsystem>();
	TestNotNull(TEXT("Subsystem instantiated"), Subsystem);

	// Simulate 20 frames at 0.016s (~60 FPS)
	for (int32 i = 0; i < 20; ++i)
	{
		Subsystem->SimulateTick(0.016f);
	}

	TestNearlyEqual(TEXT("Average FPS is ~62.5"), Subsystem->GetAverageFps(), 1.0f / 0.016f, 1.0f);

	// Inject a 50ms spike (0.050s)
	Subsystem->SimulateTick(0.050f);
	TestNearlyEqual(TEXT("Worst frame ms recorded the spike (50ms)"), Subsystem->GetWorstFrameMs(), 50.0f, 0.1f);

	return true;
}

// 8. Acceptance Criterion 1 & 2: Melee Engagement Distance (100 units) and facing alignment evaluation
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayEngagementDistanceTest, "ShunyaGame.AutoPlay.EngagementDistance", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayEngagementDistanceTest::RunTest(const FString& Parameters)
{
	// AC 1: MeleeEngagementDistance must be exactly 100.0f
	TestEqual(TEXT("MeleeEngagementDistance is 100.0f"), UCombatAutoPlaySubsystem::MeleeEngagementDistance, 100.0f);

	// Test IsReadyToMeleeAttack helper
	const FVector ForwardVector(1.0f, 0.0f, 0.0f);
	const FVector TargetAhead(1.0f, 0.0f, 0.0f);
	const FVector TargetBehind(-1.0f, 0.0f, 0.0f);
	const FVector TargetSide(0.0f, 1.0f, 0.0f);

	// Within 100 units and facing target -> ready
	TestTrue(TEXT("Ready when distance is 80 units and facing target"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(80.0f, ForwardVector, TargetAhead));

	TestTrue(TEXT("Ready when distance is exactly 100 units and facing target"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(100.0f, ForwardVector, TargetAhead));

	// Outside 100 units even if facing target -> not ready
	TestFalse(TEXT("Not ready when distance is 105 units even if facing target"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(105.0f, ForwardVector, TargetAhead));

	TestFalse(TEXT("Not ready when distance is 140 units (old threshold)"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(140.0f, ForwardVector, TargetAhead));

	// Inside 100 units but NOT facing target -> not ready
	TestFalse(TEXT("Not ready when inside 80 units but facing away"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(80.0f, ForwardVector, TargetBehind));

	TestFalse(TEXT("Not ready when inside 80 units but facing perpendicular (90 deg)"),
		UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(80.0f, ForwardVector, TargetSide));

	return true;
}

// 9. Acceptance Criterion 4: Evasive dodge gating (Health <= 50% AND Stamina > 50)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayDodgeStaminaGateTest, "ShunyaGame.AutoPlay.DodgeStaminaGate", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayDodgeStaminaGateTest::RunTest(const FString& Parameters)
{
	const float MaxHealth = 100.0f;
	const bool bInAttackRange = true;
	const float EnemyAttackCooldown = 0.1f; // Attacking

	// Case 1: Low health (40/100 = 40% <= 50%) and high stamina (60 > 50) -> DODGE ALLOWED
	TestTrue(TEXT("Dodge allowed when health <= 50% and stamina > 50"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(40.0f, MaxHealth, 60.0f, bInAttackRange, EnemyAttackCooldown));

	// Case 2: Exact health boundary (50/100 = 50% <= 50%) and stamina 50.1f (> 50) -> DODGE ALLOWED
	TestTrue(TEXT("Dodge allowed at exactly 50% health and stamina > 50"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(50.0f, MaxHealth, 50.1f, bInAttackRange, EnemyAttackCooldown));

	// Case 3: Low health (30/100) but stamina exactly 50.0f (NOT > 50) -> DODGE INHIBITED
	TestFalse(TEXT("Dodge inhibited when stamina is exactly 50.0f"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(30.0f, MaxHealth, 50.0f, bInAttackRange, EnemyAttackCooldown));

	// Case 4: Low health (30/100) and stamina < 50.0f (30) -> DODGE INHIBITED
	TestFalse(TEXT("Dodge inhibited when stamina is low (30.0f)"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(30.0f, MaxHealth, 30.0f, bInAttackRange, EnemyAttackCooldown));

	// Case 5: High health (80/100 > 50%) even with plenty of stamina (90 > 50) -> DODGE INHIBITED
	TestFalse(TEXT("Dodge inhibited when health is high (80/100)"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(80.0f, MaxHealth, 90.0f, bInAttackRange, EnemyAttackCooldown));

	// Case 6: Exact boundary health 51/100 (51% > 50%) with high stamina -> DODGE INHIBITED
	TestFalse(TEXT("Dodge inhibited at 51% health"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(51.0f, MaxHealth, 100.0f, bInAttackRange, EnemyAttackCooldown));

	// Case 7: Low health, high stamina, but enemy is NOT in attack range or striking -> NO DODGE
	TestFalse(TEXT("Dodge not triggered when enemy is not striking"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(40.0f, MaxHealth, 80.0f, false, EnemyAttackCooldown));
	TestFalse(TEXT("Dodge not triggered when enemy attack cooldown > 0.2s"),
		UCombatAutoPlaySubsystem::ShouldEvasiveDodge(40.0f, MaxHealth, 80.0f, bInAttackRange, 1.0f));

	return true;
}

// 10. Acceptance Criterion 3 & 5: Nearest living enemy targeting selection and death filtering
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatAutoPlayTargetingSelectionTest, "ShunyaGame.AutoPlay.TargetingSelection", ShunyaAutoPlayTests::Flags)
bool FCombatAutoPlayTargetingSelectionTest::RunTest(const FString& Parameters)
{
	AEnemyCharacter* Enemy1 = NewObject<AEnemyCharacter>();
	AEnemyCharacter* Enemy2 = NewObject<AEnemyCharacter>();
	AEnemyCharacter* Enemy3 = NewObject<AEnemyCharacter>();

	TestNotNull(TEXT("Enemy1 instantiated"), Enemy1);
	TestNotNull(TEXT("Enemy2 instantiated"), Enemy2);
	TestNotNull(TEXT("Enemy3 instantiated"), Enemy3);

	if (!Enemy1 || !Enemy2 || !Enemy3)
	{
		return false;
	}

	const FVector PlayerPos(0.0f, 0.0f, 0.0f);
	Enemy1->SetActorLocation(FVector(300.0f, 0.0f, 0.0f)); // Dist 300
	Enemy2->SetActorLocation(FVector(150.0f, 0.0f, 0.0f)); // Dist 150 (nearest)
	Enemy3->SetActorLocation(FVector(500.0f, 0.0f, 0.0f)); // Dist 500

	TArray<AEnemyCharacter*> Candidates = { Enemy1, Enemy2, Enemy3 };

	// Nearest alive should be Enemy2 (dist 150)
	AEnemyCharacter* Best = UCombatAutoPlaySubsystem::SelectNearestAliveEnemy(PlayerPos, Candidates);
	TestEqual(TEXT("Selects nearest alive enemy (Enemy2 at 150)"), Best, Enemy2);

	// If Enemy2 is dead (health reduced to 0), it should pick Enemy1 (dist 300)
	if (UHealthComponent* HC2 = Enemy2->GetHealthComponent())
	{
		HC2->ApplyDamage(1000.0f);
	}
	AEnemyCharacter* BestAfterDeath = UCombatAutoPlaySubsystem::SelectNearestAliveEnemy(PlayerPos, Candidates);
	TestEqual(TEXT("Selects next nearest living enemy after Enemy2 dies (Enemy1 at 300)"), BestAfterDeath, Enemy1);

	// If Enemy1 also dies, it should acquire Enemy3 (dist 500)
	if (UHealthComponent* HC1 = Enemy1->GetHealthComponent())
	{
		HC1->ApplyDamage(1000.0f);
	}
	AEnemyCharacter* BestAfterSecondDeath = UCombatAutoPlaySubsystem::SelectNearestAliveEnemy(PlayerPos, Candidates);
	TestEqual(TEXT("Selects Enemy3 when Enemy1 dies"), BestAfterSecondDeath, Enemy3);

	// If all enemies die, returns nullptr
	if (UHealthComponent* HC3 = Enemy3->GetHealthComponent())
	{
		HC3->ApplyDamage(1000.0f);
	}
	AEnemyCharacter* NoEnemy = UCombatAutoPlaySubsystem::SelectNearestAliveEnemy(PlayerPos, Candidates);
	TestNull(TEXT("Returns nullptr when all candidates are dead"), NoEnemy);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
