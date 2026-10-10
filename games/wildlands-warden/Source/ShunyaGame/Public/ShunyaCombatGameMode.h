// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "ShunyaCombatTypes.h"
#include "ShunyaCombatGameMode.generated.h"

class AEnemyCharacter;
class APlayerCharacter;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWaveStartedSignature, int32, WaveNumber);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWaveClearedSignature, int32, WaveNumber);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnMatchStateChangedSignature, ECombatMatchState, NewState);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnScoreChangedSignature, int32, NewScore, int32, Delta);

/**
 * AShunyaCombatGameMode
 * Combat game mode managing wave lifecycle, enemy spawn timers, score calculation,
 * defeat condition on player death, and victory condition upon clearing wave 3.
 */
UCLASS()
class SHUNYAGAME_API AShunyaCombatGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AShunyaCombatGameMode();

	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Direct access to wave combat rules */
	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	const FWaveCombatRules& GetRules() const { return CombatRules; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	ECombatMatchState GetCombatMatchState() const { return CombatRules.MatchState; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	int32 GetCurrentWave() const { return CombatRules.CurrentWave; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	int32 GetActiveEnemyCount() const { return CombatRules.ActiveEnemies; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	int32 GetScore() const { return CombatRules.Score; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	float GetElapsedTime() const { return CombatRules.ElapsedTime; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	bool IsInIntermission() const { return CombatRules.bInIntermission; }

	UFUNCTION(BlueprintPure, Category="Combat|GameMode")
	float GetInterWaveCountdown() const { return CombatRules.InterWaveCountdown; }

	/** Starts or restarts the match */
	UFUNCTION(BlueprintCallable, Category="Combat|GameMode")
	void StartMatch();

	/** Restarts match and resets player and enemies */
	UFUNCTION(BlueprintCallable, Category="Combat|GameMode")
	void RestartMatch();

	/** Handle enemy being killed */
	UFUNCTION()
	void OnEnemyKilled(AActor* DeadActor);

	/** Handle player death */
	UFUNCTION()
	void OnPlayerKilled(AActor* DeadActor);

	/** Spawns next enemy in current wave if spawning sequentially */
	UFUNCTION(BlueprintCallable, Category="Combat|GameMode")
	void SpawnEnemiesForCurrentWave();

	/** Cleans up all currently alive enemy instances */
	UFUNCTION(BlueprintCallable, Category="Combat|GameMode")
	void ClearAllEnemies();

	// Delegates
	UPROPERTY(BlueprintAssignable, Category="Combat|GameMode")
	FOnWaveStartedSignature OnWaveStarted;

	UPROPERTY(BlueprintAssignable, Category="Combat|GameMode")
	FOnWaveClearedSignature OnWaveCleared;

	UPROPERTY(BlueprintAssignable, Category="Combat|GameMode")
	FOnMatchStateChangedSignature OnMatchStateChanged;

	UPROPERTY(BlueprintAssignable, Category="Combat|GameMode")
	FOnScoreChangedSignature OnScoreChanged;

protected:
	/** Internal rule instance */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Combat|GameMode")
	FWaveCombatRules CombatRules;

	/** Tracked active enemies in the world */
	UPROPERTY(Transient)
	TArray<TWeakObjectPtr<AEnemyCharacter>> SpawnedEnemies;

	/** Class used to spawn enemies */
	UPROPERTY(EditDefaultsOnly, Category="Combat|GameMode")
	TSubclassOf<AEnemyCharacter> EnemyClass;

	/** Perimeter spawn radius (default 1200.0) */
	UPROPERTY(EditDefaultsOnly, Category="Combat|GameMode")
	float SpawnRadius;

	/** Stagger timer between spawning individual enemies */
	UPROPERTY(EditDefaultsOnly, Category="Combat|GameMode")
	float SpawnStaggerDelay;

	/** Queue of remaining spawn transforms for the active wave */
	TArray<FTransform> PendingSpawnQueue;
	float SpawnTimer;
	float CurrentWaveHealthMultiplier;

	void ProcessSpawnQueue(float DeltaTime);
	void TransitionMatchState(ECombatMatchState NewState);
	void BeginWave(int32 WaveNumber);
	void BindPlayerDeathListener();
};
