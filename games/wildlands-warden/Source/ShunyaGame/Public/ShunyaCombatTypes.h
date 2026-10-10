// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "ShunyaCombatTypes.generated.h"

UENUM(BlueprintType)
enum class ECombatMatchState : uint8
{
	NotStarted,
	InProgress,
	Victory,
	GameOver
};

USTRUCT(BlueprintType)
struct SHUNYAGAME_API FWaveDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Wave")
	int32 WaveNumber = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Wave")
	int32 EnemyCount = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Wave")
	float HealthMultiplier = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Wave")
	float EnemyHealth = 50.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Wave")
	float InterWaveDelay = 3.0f;
};

/**
 * FWaveCombatRules
 * Pure logic and state management struct adhering to ADR-002.
 * Can be fully exercised headlessly without a running UWorld.
 */
USTRUCT(BlueprintType)
struct SHUNYAGAME_API FWaveCombatRules
{
	GENERATED_BODY()

	FWaveCombatRules();

	// Config / Defaults
	static constexpr int32 TotalWaves = 3;
	static constexpr int32 BaseKillScore = 100;
	static constexpr float DefaultInterWaveDelay = 3.0f;
	static constexpr float DefaultSpawnRadius = 1200.0f;
	static constexpr float DefaultSpawnStagger = 0.5f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	ECombatMatchState MatchState;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	int32 CurrentWave;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	int32 ActiveEnemies;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	int32 TotalEnemiesSpawnedInWave;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	int32 TotalEnemiesDefeated;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	int32 Score;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	float ElapsedTime;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	float InterWaveCountdown;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	bool bInIntermission;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Rules")
	bool bWaveInProgress;

	/** Start a fresh match */
	void StartMatch();

	/** Reset match to initial state (supports restart) */
	void ResetMatch();

	/** Start a specific wave (1, 2, or 3) */
	bool StartWave(int32 WaveIndex);

	/** Called when an enemy is defeated */
	void RecordEnemyKill();

	/** Called when player health changes or drops to 0 */
	void HandlePlayerDeath();

	/** Advance timers (inter-wave intermission, elapsed time) */
	void AdvanceTime(float DeltaTime);

	/** Helper to get wave definition for 1..3 */
	static FWaveDefinition GetWaveDefinition(int32 WaveNumber);

	/** Helper to calculate perimeter spawn positions at a radius R */
	static TArray<FVector> CalculateSpawnLocations(int32 WaveNumber, float Radius = 1200.0f, const FVector& Center = FVector::ZeroVector);

	/** Helper to check if current wave is cleared */
	bool IsWaveCleared() const;

	/** Helper to check if match is won */
	bool IsVictory() const { return MatchState == ECombatMatchState::Victory; }

	/** Helper to check if match is over (loss) */
	bool IsGameOver() const { return MatchState == ECombatMatchState::GameOver; }

	/** Helper to check if match is in progress */
	bool IsInProgress() const { return MatchState == ECombatMatchState::InProgress; }
};
