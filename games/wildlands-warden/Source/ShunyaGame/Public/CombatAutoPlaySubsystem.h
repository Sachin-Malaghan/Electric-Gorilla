// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "CombatAutoPlaySubsystem.generated.h"

class APlayerCharacter;
class AEnemyCharacter;

/**
 * UCombatAutoPlaySubsystem
 * 
 * QA Autoplay bot world subsystem that automates player inputs under -ShunyaAutoPlay,
 * takes the playtest screenshot, tracks performance telemetry, and outputs structured test results.
 */
UCLASS()
class SHUNYAGAME_API UCombatAutoPlaySubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	UCombatAutoPlaySubsystem();

	// UTickableWorldSubsystem interface
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	/** Static helper to check whether -ShunyaAutoPlay is specified on command line */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static bool IsAutoPlayEnabled();

	/** Static helper to check if auto play should run given command line and world type */
	static bool ShouldRunAutoPlay(bool bCommandLineParam, EWorldType::Type WorldType);

	/** Static helper to determine steering input towards a target */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static FVector CalculateSteeringDirection(const FVector& CurrentPos, const FVector& TargetPos);

	/** Static helper to calculate control rotation / yaw to face a target */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static FRotator CalculateAimRotation(const FVector& CurrentPos, const FVector& TargetPos);

	/** Static helper to format the final playtest log string */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static FString FormatPlaytestOutput(const FString& Result, int32 Score, int32 Health, float Seconds, float AvgFps, float WorstFrameMs, int32 MissingContent = 0);

	/** Find nearest alive enemy in world relative to a given position */
	AEnemyCharacter* FindNearestAliveEnemy(const FVector& FromLocation) const;

	/** Pure static helper to find nearest alive enemy from a candidate list without requiring UWorld iterator */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static AEnemyCharacter* SelectNearestAliveEnemy(const FVector& FromLocation, const TArray<AEnemyCharacter*>& Candidates);

	/** Static helper to evaluate if bot is in engagement range and facing target */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static bool IsReadyToMeleeAttack(float DistanceToTarget, const FVector& ForwardVector, const FVector& DirectionToTarget);

	/** Get current performance metrics */
	float GetAverageFps() const;
	float GetWorstFrameMs() const { return WorstFrameMs; }
	float GetMatchSeconds() const { return MatchSeconds; }
	bool HasRequestedScreenshot() const { return bScreenshotRequested; }
	bool HasCompletedTest() const { return bTestCompleted; }

	// Test injection helpers
	void SimulateTick(float DeltaTime);

	// Configurable timings
	static constexpr float ScreenshotTime = 3.0f;
	static constexpr float TimeoutSeconds = 150.0f;
	static constexpr float MeleeEngagementDistance = 100.0f; // Inside attack range (150-180)
	static constexpr float DodgeThresholdDistance = 160.0f;  // Dodge if enemy attacks / is very close

	/** Static helper to evaluate if autoplay bot should dodge given health and stamina */
	UFUNCTION(BlueprintPure, Category="AutoPlay")
	static bool ShouldEvasiveDodge(float CurrentHealth, float MaxHealth, float CurrentStamina, bool bEnemyInAttackRange, float EnemyAttackCooldownTimer);

	/** Autoplay bot damage multiplier when running under -ShunyaAutoPlay */
	static constexpr float AutoPlayDamageMultiplier = 2.0f;

protected:
	/** Execute combat AI decision logic each tick */
	void UpdateBotBehavior(float DeltaTime);

	/** Finish playtest match with status, log result and request exit */
	void CompletePlaytest(const FString& Result);

private:
	bool bScreenshotRequested = false;
	bool bTestCompleted = false;
	bool bExitRequested = false;
	float ExitDelayTimer = 0.0f;

	float MatchSeconds = 0.0f;
	int64 FrameCount = 0;
	float TotalFrameTime = 0.0f;
	float WorstFrameMs = 0.0f;

	// Bot attack pacing
	float AttackTimer = 0.0f;
};
