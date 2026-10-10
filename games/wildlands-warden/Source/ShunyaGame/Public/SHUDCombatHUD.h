// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "ShunyaCombatTypes.h"
#include "SHUDCombatHUD.generated.h"

class AShunyaCombatGameMode;
class APlayerCharacter;
class UHealthComponent;
class UStaminaComponent;

/**
 * ASHUDCombatHUD
 * Canvas-based HUD drawing player health/stamina bars, active wave, score,
 * and full-screen Game Over and Victory screens with restart prompt.
 * Strictly uses Canvas DrawRect and DrawText with zero UMG/Slate dependencies.
 */
UCLASS()
class SHUNYAGAME_API ASHUDCombatHUD : public AHUD
{
	GENERATED_BODY()

public:
	ASHUDCombatHUD();

	virtual void DrawHUD() override;

	/** Restart game / match helper */
	UFUNCTION(BlueprintCallable, Category="Combat|HUD")
	void RestartGame();

	// --- Pure Static Formatting Helpers (testable headless without UWorld or Canvas) ---

	/** Formats wave string: "WAVE: {Wave} / {TotalWaves}" (e.g. "WAVE: 1 / 3") */
	static FString FormatWaveString(int32 CurrentWave, int32 TotalWaves = 3);

	/** Formats score string: "SCORE: {Score}" */
	static FString FormatScoreString(int32 Score);

	/** Formats enemies remaining string: "ENEMIES: {Count}" */
	static FString FormatEnemiesRemainingString(int32 RemainingCount);

	/** Formats time string: "TIME: MM:SS" */
	static FString FormatTimeString(float ElapsedSeconds);

	/** Formats health text: "HP: {Current} / {Max}" */
	static FString FormatHealthString(float CurrentHP, float MaxHP);

	/** Formats stamina text: "STAMINA: {Current} / {Max}" */
	static FString FormatStaminaString(float CurrentStamina, float MaxStamina);

	/** Formats wave clear announcement */
	static FString FormatWaveClearedString(int32 CompletedWave);

	/** Formats next wave countdown announcement */
	static FString FormatNextWaveCountdownString(float CountdownSeconds);

	/** Formats defeat banner string */
	static FString FormatDefeatedWaveString(int32 Wave, int32 TotalWaves = 3);

	/** Formats enemies defeated summary */
	static FString FormatEnemiesDefeatedString(int32 DefeatedCount);

	/** Formats clear time summary */
	static FString FormatClearTimeString(float ElapsedSeconds);

	/** Formats surviving health summary */
	static FString FormatSurvivingHealthString(float CurrentHP, float MaxHP = 100.0f);

	/** Computes health bar fill color based on percentage (interpolates green to red below 30%) */
	static FLinearColor GetHealthBarColor(float HealthFraction);

	/** Computes stamina bar fill color */
	static FLinearColor GetStaminaBarColor();

	// --- Constants & Layout specifications (GDD Section 7) ---
	static const FString VictoryBannerText;
	static const FString GameOverBannerText;
	static const FString RestartPromptVictoryText;
	static const FString RestartPromptGameOverText;

protected:
	/** Renders in-game combat HUD elements */
	void DrawCombatHUD(APlayerCharacter* PlayerChar, AShunyaCombatGameMode* GameMode);

	/** Renders Game Over overlay screen */
	void DrawGameOverScreen(AShunyaCombatGameMode* GameMode);

	/** Renders Victory overlay screen */
	void DrawVictoryScreen(APlayerCharacter* PlayerChar, AShunyaCombatGameMode* GameMode);

	/** Helper to draw centered text on Canvas */
	void DrawCenteredText(const FString& Text, const FLinearColor& Color, float YPos, float Scale = 1.0f);

	/** Cached default font */
	UPROPERTY(Transient)
	UFont* HUDFont;
};
