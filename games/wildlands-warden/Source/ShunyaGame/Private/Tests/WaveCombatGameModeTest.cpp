// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "ShunyaCombatTypes.h"
#include "ShunyaCombatGameMode.h"
#include "Characters/EnemyCharacter.h"
#include "Characters/PlayerCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaWaveTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// 1. Wave Configuration Verification (Wave 1: 3, Wave 2: 5, Wave 3: 8 with 1.25x HP multiplier)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveDefinitionsTest, "ShunyaGame.Wave.Definitions", ShunyaWaveTests::Flags)
bool FWaveDefinitionsTest::RunTest(const FString& Parameters)
{
	FWaveDefinition Wave1 = FWaveCombatRules::GetWaveDefinition(1);
	TestEqual(TEXT("Wave 1 enemy count is 3"), Wave1.EnemyCount, 3);
	TestEqual(TEXT("Wave 1 health multiplier is 1.0"), Wave1.HealthMultiplier, 1.0f);
	TestEqual(TEXT("Wave 1 enemy base health is 50.0"), Wave1.EnemyHealth, 50.0f);
	TestEqual(TEXT("Wave 1 inter-wave delay is 3.0s"), Wave1.InterWaveDelay, 3.0f);

	FWaveDefinition Wave2 = FWaveCombatRules::GetWaveDefinition(2);
	TestEqual(TEXT("Wave 2 enemy count is 5"), Wave2.EnemyCount, 5);
	TestEqual(TEXT("Wave 2 health multiplier is 1.0"), Wave2.HealthMultiplier, 1.0f);
	TestEqual(TEXT("Wave 2 enemy base health is 50.0"), Wave2.EnemyHealth, 50.0f);
	TestEqual(TEXT("Wave 2 inter-wave delay is 3.0s"), Wave2.InterWaveDelay, 3.0f);

	FWaveDefinition Wave3 = FWaveCombatRules::GetWaveDefinition(3);
	TestEqual(TEXT("Wave 3 enemy count is 8"), Wave3.EnemyCount, 8);
	TestEqual(TEXT("Wave 3 health multiplier is 1.25"), Wave3.HealthMultiplier, 1.25f);
	TestEqual(TEXT("Wave 3 enemy base health is 62.5"), Wave3.EnemyHealth, 62.5f);

	return true;
}

// 2. Spawn Point Perimeter Layout Calculation
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveSpawnPerimeterTest, "ShunyaGame.Wave.SpawnPerimeter", ShunyaWaveTests::Flags)
bool FWaveSpawnPerimeterTest::RunTest(const FString& Parameters)
{
	const float Radius = 1200.0f;
	TArray<FVector> W1Spawns = FWaveCombatRules::CalculateSpawnLocations(1, Radius);
	TestEqual(TEXT("Wave 1 produces 3 spawn points"), W1Spawns.Num(), 3);
	for (const FVector& Loc : W1Spawns)
	{
		float Dist2D = FVector2D(Loc.X, Loc.Y).Size();
		TestNearlyEqual(TEXT("Wave 1 spawn point is on perimeter radius"), Dist2D, Radius, 1.0f);
	}

	TArray<FVector> W2Spawns = FWaveCombatRules::CalculateSpawnLocations(2, Radius);
	TestEqual(TEXT("Wave 2 produces 5 spawn points"), W2Spawns.Num(), 5);

	TArray<FVector> W3Spawns = FWaveCombatRules::CalculateSpawnLocations(3, Radius);
	TestEqual(TEXT("Wave 3 produces 8 spawn points"), W3Spawns.Num(), 8);

	return true;
}

// 3. Wave Progression and Score Accumulation (+100 pts per kill)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveProgressionAndScoreTest, "ShunyaGame.Wave.ProgressionAndScore", ShunyaWaveTests::Flags)
bool FWaveProgressionAndScoreTest::RunTest(const FString& Parameters)
{
	FWaveCombatRules Rules;
	Rules.StartMatch();

	TestEqual(TEXT("Match starts in InProgress"), Rules.MatchState, ECombatMatchState::InProgress);
	TestEqual(TEXT("Current wave is 1"), Rules.CurrentWave, 1);
	TestEqual(TEXT("Wave 1 starts with 3 active enemies"), Rules.ActiveEnemies, 3);
	TestEqual(TEXT("Initial score is 0"), Rules.Score, 0);

	// Defeat enemy 1
	Rules.RecordEnemyKill();
	TestEqual(TEXT("Active enemies decreased to 2"), Rules.ActiveEnemies, 2);
	TestEqual(TEXT("Score increased to 100"), Rules.Score, 100);

	// Defeat enemy 2
	Rules.RecordEnemyKill();
	TestEqual(TEXT("Active enemies decreased to 1"), Rules.ActiveEnemies, 1);
	TestEqual(TEXT("Score increased to 200"), Rules.Score, 200);

	// Defeat enemy 3 (clears wave 1)
	Rules.RecordEnemyKill();
	TestEqual(TEXT("Active enemies decreased to 0"), Rules.ActiveEnemies, 0);
	TestEqual(TEXT("Score increased to 300"), Rules.Score, 300);
	TestTrue(TEXT("Wave 1 is cleared"), Rules.IsWaveCleared());
	TestTrue(TEXT("Intermission started"), Rules.bInIntermission);
	TestNearlyEqual(TEXT("Intermission countdown initialized to 3.0s"), Rules.InterWaveCountdown, 3.0f, 0.01f);

	// Advance intermission timer partially
	Rules.AdvanceTime(1.5f);
	TestNearlyEqual(TEXT("Intermission countdown remaining 1.5s"), Rules.InterWaveCountdown, 1.5f, 0.01f);
	TestEqual(TEXT("Still wave 1 during intermission"), Rules.CurrentWave, 1);

	// Advance intermission timer past remaining duration (1.6s)
	Rules.AdvanceTime(1.6f);
	TestFalse(TEXT("Intermission ended"), Rules.bInIntermission);
	TestEqual(TEXT("Escalated to Wave 2"), Rules.CurrentWave, 2);
	TestEqual(TEXT("Wave 2 starts with 5 active enemies"), Rules.ActiveEnemies, 5);

	// Defeat 5 enemies in Wave 2
	for (int32 i = 0; i < 5; ++i)
	{
		Rules.RecordEnemyKill();
	}
	TestEqual(TEXT("Score is now 800 (3*100 + 5*100)"), Rules.Score, 800);
	TestTrue(TEXT("Wave 2 intermission started"), Rules.bInIntermission);

	// Advance intermission into Wave 3
	Rules.AdvanceTime(3.1f);
	TestEqual(TEXT("Escalated to Wave 3"), Rules.CurrentWave, 3);
	TestEqual(TEXT("Wave 3 starts with 8 active enemies"), Rules.ActiveEnemies, 8);

	return true;
}

// 4. Victory Condition Trigger upon clearing Wave 3
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveVictoryConditionTest, "ShunyaGame.Wave.VictoryCondition", ShunyaWaveTests::Flags)
bool FWaveVictoryConditionTest::RunTest(const FString& Parameters)
{
	FWaveCombatRules Rules;
	Rules.StartMatch();

	// Clear Wave 1 (3 enemies)
	for (int32 i = 0; i < 3; ++i)
	{
		Rules.RecordEnemyKill();
	}
	Rules.AdvanceTime(3.0f); // Transition to Wave 2

	// Clear Wave 2 (5 enemies)
	for (int32 i = 0; i < 5; ++i)
	{
		Rules.RecordEnemyKill();
	}
	Rules.AdvanceTime(3.0f); // Transition to Wave 3

	TestEqual(TEXT("At Wave 3"), Rules.CurrentWave, 3);
	TestEqual(TEXT("Active enemies is 8"), Rules.ActiveEnemies, 8);

	// Defeat 7 enemies
	for (int32 i = 0; i < 7; ++i)
	{
		Rules.RecordEnemyKill();
	}
	TestEqual(TEXT("1 enemy remaining"), Rules.ActiveEnemies, 1);
	TestEqual(TEXT("Still InProgress"), Rules.MatchState, ECombatMatchState::InProgress);

	// Defeat 8th enemy -> Victory!
	Rules.RecordEnemyKill();
	TestEqual(TEXT("Active enemies is 0"), Rules.ActiveEnemies, 0);
	TestEqual(TEXT("Match transitioned to Victory"), Rules.MatchState, ECombatMatchState::Victory);
	TestTrue(TEXT("IsVictory helper returns true"), Rules.IsVictory());
	TestEqual(TEXT("Total score after all 16 kills is 1600"), Rules.Score, 1600);
	TestEqual(TEXT("Total enemies defeated is 16"), Rules.TotalEnemiesDefeated, 16);

	return true;
}

// 5. Defeat Condition Trigger on Player Death
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveGameOverConditionTest, "ShunyaGame.Wave.GameOverCondition", ShunyaWaveTests::Flags)
bool FWaveGameOverConditionTest::RunTest(const FString& Parameters)
{
	FWaveCombatRules Rules;
	Rules.StartMatch();

	TestEqual(TEXT("Match InProgress"), Rules.MatchState, ECombatMatchState::InProgress);

	// Player dies during Wave 1
	Rules.HandlePlayerDeath();
	TestEqual(TEXT("Match transitioned to GameOver"), Rules.MatchState, ECombatMatchState::GameOver);
	TestTrue(TEXT("IsGameOver helper returns true"), Rules.IsGameOver());
	TestFalse(TEXT("Wave is no longer considered in progress"), Rules.bWaveInProgress);

	// Kills after GameOver do not modify score
	int32 PrevScore = Rules.Score;
	Rules.RecordEnemyKill();
	TestEqual(TEXT("Score does not increase after GameOver"), Rules.Score, PrevScore);

	return true;
}

// 6. Match Restart without dangling references or state
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWaveMatchRestartTest, "ShunyaGame.Wave.MatchRestart", ShunyaWaveTests::Flags)
bool FWaveMatchRestartTest::RunTest(const FString& Parameters)
{
	FWaveCombatRules Rules;
	Rules.StartMatch();

	// Advance some state
	Rules.RecordEnemyKill();
	Rules.AdvanceTime(10.0f);
	Rules.HandlePlayerDeath();
	TestEqual(TEXT("Match is GameOver"), Rules.MatchState, ECombatMatchState::GameOver);

	// Restart
	Rules.StartMatch();
	TestEqual(TEXT("State reset to InProgress"), Rules.MatchState, ECombatMatchState::InProgress);
	TestEqual(TEXT("Wave reset to 1"), Rules.CurrentWave, 1);
	TestEqual(TEXT("Active enemies reset to 3"), Rules.ActiveEnemies, 3);
	TestEqual(TEXT("Score reset to 0"), Rules.Score, 0);
	TestEqual(TEXT("Total enemies defeated reset to 0"), Rules.TotalEnemiesDefeated, 0);
	TestNearlyEqual(TEXT("Elapsed time reset to 0"), Rules.ElapsedTime, 0.0f, 0.001f);
	TestFalse(TEXT("Not in intermission"), Rules.bInIntermission);

	return true;
}

// 7. CombatGameMode Class Registration and Reflection Test
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCombatGameModeClassTest, "ShunyaGame.Wave.GameModeClassExists", ShunyaWaveTests::Flags)
bool FCombatGameModeClassTest::RunTest(const FString& Parameters)
{
	const UClass* CombatGameModeClass = AShunyaCombatGameMode::StaticClass();
	TestNotNull(TEXT("AShunyaCombatGameMode is registered with the reflection system"), CombatGameModeClass);
	TestTrue(TEXT("AShunyaCombatGameMode derives from AGameModeBase"), CombatGameModeClass && CombatGameModeClass->IsChildOf(AGameModeBase::StaticClass()));

	// Instantiate game mode in transient package to verify default properties
	AShunyaCombatGameMode* GameMode = NewObject<AShunyaCombatGameMode>();
	TestNotNull(TEXT("GameMode instantiated successfully"), GameMode);
	if (GameMode)
	{
		TestEqual(TEXT("Initial rule state is NotStarted"), GameMode->GetCombatMatchState(), ECombatMatchState::NotStarted);
		TestEqual(TEXT("Initial score is 0"), GameMode->GetScore(), 0);

		GameMode->StartMatch();
		TestEqual(TEXT("After StartMatch, state is InProgress"), GameMode->GetCombatMatchState(), ECombatMatchState::InProgress);
		TestEqual(TEXT("After StartMatch, wave is 1"), GameMode->GetCurrentWave(), 1);
		TestEqual(TEXT("After StartMatch, active enemies is 3"), GameMode->GetActiveEnemyCount(), 3);

		// Test restart
		GameMode->RestartMatch();
		TestEqual(TEXT("After RestartMatch, state is InProgress"), GameMode->GetCombatMatchState(), ECombatMatchState::InProgress);
		TestEqual(TEXT("After RestartMatch, wave is 1"), GameMode->GetCurrentWave(), 1);
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
