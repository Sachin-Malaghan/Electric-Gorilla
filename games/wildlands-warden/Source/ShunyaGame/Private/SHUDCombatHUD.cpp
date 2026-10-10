// Copyright Epic Games, Inc. All Rights Reserved.

#include "SHUDCombatHUD.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Characters/PlayerCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"
#include "ShunyaCombatGameMode.h"
#include "UObject/ConstructorHelpers.h"

const FString ASHUDCombatHUD::VictoryBannerText = TEXT("VICTORY ACHIEVED");
const FString ASHUDCombatHUD::GameOverBannerText = TEXT("GAME OVER");
const FString ASHUDCombatHUD::RestartPromptVictoryText = TEXT("PRESS [R] TO PLAY AGAIN");
const FString ASHUDCombatHUD::RestartPromptGameOverText = TEXT("PRESS [R] TO RESTART ARENA");

ASHUDCombatHUD::ASHUDCombatHUD()
	: HUDFont(nullptr)
{
	static ConstructorHelpers::FObjectFinder<UFont> FontFinder(TEXT("/Engine/EngineFonts/Roboto"));
	if (FontFinder.Succeeded())
	{
		HUDFont = FontFinder.Object;
	}
}

void ASHUDCombatHUD::RestartGame()
{
	if (UWorld* World = GetWorld())
	{
		if (AShunyaCombatGameMode* GM = Cast<AShunyaCombatGameMode>(World->GetAuthGameMode()))
		{
			GM->RestartMatch();
		}
	}
}

FString ASHUDCombatHUD::FormatWaveString(int32 CurrentWave, int32 TotalWaves)
{
	return FString::Printf(TEXT("WAVE: %d / %d"), CurrentWave, TotalWaves);
}

FString ASHUDCombatHUD::FormatScoreString(int32 Score)
{
	return FString::Printf(TEXT("SCORE: %05d"), FMath::Max(0, Score));
}

FString ASHUDCombatHUD::FormatEnemiesRemainingString(int32 RemainingCount)
{
	return FString::Printf(TEXT("ENEMIES: %d REMAINING"), FMath::Max(0, RemainingCount));
}

FString ASHUDCombatHUD::FormatTimeString(float ElapsedSeconds)
{
	const int32 TotalSeconds = FMath::Max(0, FMath::FloorToInt(ElapsedSeconds));
	const int32 Minutes = TotalSeconds / 60;
	const int32 Seconds = TotalSeconds % 60;
	return FString::Printf(TEXT("TIME: %02d:%02d"), Minutes, Seconds);
}

FString ASHUDCombatHUD::FormatHealthString(float CurrentHP, float MaxHP)
{
	const int32 Cur = FMath::Clamp(FMath::RoundToInt(CurrentHP), 0, FMath::RoundToInt(MaxHP));
	const int32 Max = FMath::RoundToInt(MaxHP);
	return FString::Printf(TEXT("HP: %d / %d"), Cur, Max);
}

FString ASHUDCombatHUD::FormatStaminaString(float CurrentStamina, float MaxStamina)
{
	const int32 Cur = FMath::Clamp(FMath::RoundToInt(CurrentStamina), 0, FMath::RoundToInt(MaxStamina));
	const int32 Max = FMath::RoundToInt(MaxStamina);
	return FString::Printf(TEXT("STAMINA: %d / %d"), Cur, Max);
}

FString ASHUDCombatHUD::FormatWaveClearedString(int32 CompletedWave)
{
	return FString::Printf(TEXT("WAVE %d CLEARED!"), CompletedWave);
}

FString ASHUDCombatHUD::FormatNextWaveCountdownString(float CountdownSeconds)
{
	return FString::Printf(TEXT("NEXT WAVE IN: %.1fs"), FMath::Max(0.0f, CountdownSeconds));
}

FString ASHUDCombatHUD::FormatDefeatedWaveString(int32 Wave, int32 TotalWaves)
{
	return FString::Printf(TEXT("DEFEATED ON WAVE: %d / %d"), Wave, TotalWaves);
}

FString ASHUDCombatHUD::FormatEnemiesDefeatedString(int32 DefeatedCount)
{
	return FString::Printf(TEXT("ENEMIES DEFEATED: %d"), FMath::Max(0, DefeatedCount));
}

FString ASHUDCombatHUD::FormatClearTimeString(float ElapsedSeconds)
{
	const int32 TotalSeconds = FMath::Max(0, FMath::FloorToInt(ElapsedSeconds));
	const int32 Minutes = TotalSeconds / 60;
	const int32 Seconds = TotalSeconds % 60;
	return FString::Printf(TEXT("CLEAR TIME: %02d:%02d"), Minutes, Seconds);
}

FString ASHUDCombatHUD::FormatSurvivingHealthString(float CurrentHP, float MaxHP)
{
	const int32 Cur = FMath::Clamp(FMath::RoundToInt(CurrentHP), 0, FMath::RoundToInt(MaxHP));
	const int32 Max = FMath::RoundToInt(MaxHP);
	return FString::Printf(TEXT("SURVIVING HEALTH: %d / %d"), Cur, Max);
}

FLinearColor ASHUDCombatHUD::GetHealthBarColor(float HealthFraction)
{
	const FLinearColor BrightGreen(0.1f, 0.85f, 0.15f, 1.0f);
	const FLinearColor Red(0.9f, 0.1f, 0.1f, 1.0f);

	HealthFraction = FMath::Clamp(HealthFraction, 0.0f, 1.0f);
	if (HealthFraction < 0.30f)
	{
		// Interpolate from Red (at 0) to Green (at 0.30)
		const float Alpha = HealthFraction / 0.30f;
		return FLinearColor::LerpUsingHSV(Red, BrightGreen, Alpha);
	}
	return BrightGreen;
}

FLinearColor ASHUDCombatHUD::GetStaminaBarColor()
{
	return FLinearColor(0.95f, 0.75f, 0.1f, 1.0f); // Golden Yellow
}

void ASHUDCombatHUD::DrawCenteredText(const FString& Text, const FLinearColor& Color, float YPos, float Scale)
{
	if (!Canvas || Text.IsEmpty())
	{
		return;
	}

	UFont* FontToUse = HUDFont ? HUDFont : GEngine->GetMediumFont();
	float TextWidth = 0.0f;
	float TextHeight = 0.0f;
	GetTextSize(Text, TextWidth, TextHeight, FontToUse, Scale);

	const float XPos = (Canvas->ClipX - TextWidth) * 0.5f;
	DrawText(Text, Color, XPos, YPos, FontToUse, Scale);
}

void ASHUDCombatHUD::DrawHUD()
{
	Super::DrawHUD();

	if (!Canvas)
	{
		return;
	}

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	APlayerController* PC = GetOwningPlayerController();
	APlayerCharacter* PlayerChar = PC ? Cast<APlayerCharacter>(PC->GetPawn()) : nullptr;
	AShunyaCombatGameMode* GameMode = Cast<AShunyaCombatGameMode>(World->GetAuthGameMode());

	ECombatMatchState MatchState = ECombatMatchState::InProgress;
	if (GameMode)
	{
		MatchState = GameMode->GetCombatMatchState();
	}

	if (MatchState == ECombatMatchState::GameOver)
	{
		DrawGameOverScreen(GameMode);
	}
	else if (MatchState == ECombatMatchState::Victory)
	{
		DrawVictoryScreen(PlayerChar, GameMode);
	}
	else
	{
		DrawCombatHUD(PlayerChar, GameMode);
	}
}

void ASHUDCombatHUD::DrawCombatHUD(APlayerCharacter* PlayerChar, AShunyaCombatGameMode* GameMode)
{
	if (!Canvas)
	{
		return;
	}

	UFont* FontToUse = HUDFont ? HUDFont : GEngine->GetMediumFont();

	// 1. Top-Left Status Bars (Player Vitals)
	float CurrentHealth = 100.0f;
	float MaxHealth = 100.0f;
	float CurrentStamina = 100.0f;
	float MaxStamina = 100.0f;

	if (PlayerChar)
	{
		if (UHealthComponent* HC = PlayerChar->GetHealthComponent())
		{
			CurrentHealth = HC->GetHealth();
			MaxHealth = HC->GetMaxHealth();
		}
		if (UStaminaComponent* SC = PlayerChar->GetStaminaComponent())
		{
			CurrentStamina = SC->GetStamina();
			MaxStamina = SC->GetMaxStamina();
		}
	}

	const float HealthFrac = MaxHealth > 0.0f ? FMath::Clamp(CurrentHealth / MaxHealth, 0.0f, 1.0f) : 0.0f;
	const float StaminaFrac = MaxStamina > 0.0f ? FMath::Clamp(CurrentStamina / MaxStamina, 0.0f, 1.0f) : 0.0f;

	const FLinearColor BgColor(0.1f, 0.1f, 0.1f, 0.8f);

	// Health Bar: X=20, Y=20, W=300, H=24
	DrawRect(BgColor, 20.0f, 20.0f, 300.0f, 24.0f);
	if (HealthFrac > 0.0f)
	{
		DrawRect(GetHealthBarColor(HealthFrac), 20.0f, 20.0f, 300.0f * HealthFrac, 24.0f);
	}
	DrawText(FormatHealthString(CurrentHealth, MaxHealth), FLinearColor::White, 24.0f, 24.0f, FontToUse, 1.0f);

	// Stamina Bar: X=20, Y=52, W=300, H=18
	DrawRect(BgColor, 20.0f, 52.0f, 300.0f, 18.0f);
	if (StaminaFrac > 0.0f)
	{
		DrawRect(GetStaminaBarColor(), 20.0f, 52.0f, 300.0f * StaminaFrac, 18.0f);
	}
	DrawText(FormatStaminaString(CurrentStamina, MaxStamina), FLinearColor::White, 24.0f, 54.0f, FontToUse, 0.9f);

	// 2. Top-Right Match Status (Active wave, score, enemies, elapsed time)
	int32 CurrentWave = 1;
	int32 RemainingEnemies = 0;
	int32 Score = 0;
	float ElapsedTime = 0.0f;
	bool bInIntermission = false;
	float InterWaveCountdown = 0.0f;

	if (GameMode)
	{
		CurrentWave = GameMode->GetCurrentWave();
		RemainingEnemies = GameMode->GetActiveEnemyCount();
		Score = GameMode->GetScore();
		ElapsedTime = GameMode->GetElapsedTime();
		bInIntermission = GameMode->IsInIntermission();
		InterWaveCountdown = GameMode->GetInterWaveCountdown();
	}

	const float RightX = FMath::Max(20.0f, Canvas->ClipX - 250.0f);
	DrawText(FormatWaveString(CurrentWave), FLinearColor::White, RightX, 20.0f, FontToUse, 1.0f);
	DrawText(FormatEnemiesRemainingString(RemainingEnemies), FLinearColor(1.0f, 0.9f, 0.2f, 1.0f), RightX, 44.0f, FontToUse, 1.0f);
	DrawText(FormatScoreString(Score), FLinearColor::White, RightX, 68.0f, FontToUse, 1.0f);
	DrawText(FormatTimeString(ElapsedTime), FLinearColor(0.8f, 0.8f, 0.8f, 1.0f), RightX, 92.0f, FontToUse, 1.0f);

	// 3. Center Reticle / Crosshair
	const float CenterX = Canvas->ClipX * 0.5f;
	const float CenterY = Canvas->ClipY * 0.5f;
	const FLinearColor CrosshairColor(1.0f, 1.0f, 1.0f, 0.75f);
	DrawRect(CrosshairColor, CenterX - 1.0f, CenterY - 6.0f, 2.0f, 12.0f);
	DrawRect(CrosshairColor, CenterX - 6.0f, CenterY - 1.0f, 12.0f, 2.0f);

	// 4. Bottom-Left Ability Indicator (Heavy Attack)
	const float AbilityY = FMath::Max(20.0f, Canvas->ClipY - 60.0f);
	if (PlayerChar)
	{
		const float HeavyCd = PlayerChar->GetHeavyAttackCooldownRemaining();
		if (HeavyCd <= 0.0f)
		{
			DrawText(TEXT("[RMB] HEAVY ATTACK: READY"), FLinearColor(0.2f, 0.9f, 1.0f, 1.0f), 20.0f, AbilityY, FontToUse, 1.1f);
		}
		else
		{
			DrawText(FString::Printf(TEXT("[RMB] HEAVY ATTACK: %.1fs"), HeavyCd), FLinearColor(0.5f, 0.5f, 0.5f, 0.8f), 20.0f, AbilityY, FontToUse, 1.1f);
		}
	}

	// 5. Inter-Wave Announcement (Center Overlay)
	if (bInIntermission)
	{
		const float AnnouncementY = Canvas->ClipY * 0.35f;
		DrawCenteredText(FormatWaveClearedString(CurrentWave), FLinearColor(1.0f, 0.84f, 0.0f, 1.0f), AnnouncementY, 2.0f);
		DrawCenteredText(FormatNextWaveCountdownString(InterWaveCountdown), FLinearColor::White, AnnouncementY + 40.0f, 1.5f);
	}
}

void ASHUDCombatHUD::DrawGameOverScreen(AShunyaCombatGameMode* GameMode)
{
	if (!Canvas)
	{
		return;
	}

	UFont* FontToUse = HUDFont ? HUDFont : GEngine->GetMediumFont();

	// Full Screen Overlay: Semi-transparent Black box
	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.75f), 0.0f, 0.0f, Canvas->ClipX, Canvas->ClipY);

	int32 Wave = 1;
	int32 Score = 0;
	int32 DefeatedCount = 0;
	if (GameMode)
	{
		const FWaveCombatRules& Rules = GameMode->GetRules();
		Wave = Rules.CurrentWave;
		Score = Rules.Score;
		DefeatedCount = Rules.TotalEnemiesDefeated;
	}

	// Centered Header
	DrawCenteredText(GameOverBannerText, FLinearColor(0.95f, 0.1f, 0.1f, 1.0f), Canvas->ClipY * 0.30f, 3.0f);

	// Wave Reached
	DrawCenteredText(FormatDefeatedWaveString(Wave), FLinearColor::White, Canvas->ClipY * 0.42f, 1.5f);

	// Final Score
	DrawCenteredText(FString::Printf(TEXT("FINAL SCORE: %d"), Score), FLinearColor(1.0f, 0.85f, 0.1f, 1.0f), Canvas->ClipY * 0.48f, 1.5f);

	// Enemies Slain
	DrawCenteredText(FormatEnemiesDefeatedString(DefeatedCount), FLinearColor::White, Canvas->ClipY * 0.54f, 1.2f);

	// Restart Prompt: Press R to Restart
	DrawCenteredText(RestartPromptGameOverText, FLinearColor(0.4f, 0.9f, 1.0f, 1.0f), Canvas->ClipY * 0.65f, 1.5f);
}

void ASHUDCombatHUD::DrawVictoryScreen(APlayerCharacter* PlayerChar, AShunyaCombatGameMode* GameMode)
{
	if (!Canvas)
	{
		return;
	}

	UFont* FontToUse = HUDFont ? HUDFont : GEngine->GetMediumFont();

	// Full Screen Overlay: Semi-transparent Dark Navy box
	DrawRect(FLinearColor(0.02f, 0.05f, 0.15f, 0.8f), 0.0f, 0.0f, Canvas->ClipX, Canvas->ClipY);

	int32 Score = 0;
	float ElapsedTime = 0.0f;
	if (GameMode)
	{
		const FWaveCombatRules& Rules = GameMode->GetRules();
		Score = Rules.Score;
		ElapsedTime = Rules.ElapsedTime;
	}

	float CurrentHealth = 100.0f;
	if (PlayerChar && PlayerChar->GetHealthComponent())
	{
		CurrentHealth = PlayerChar->GetHealthComponent()->GetHealth();
	}

	// Centered Header: "VICTORY ACHIEVED" / "VICTORY"
	DrawCenteredText(VictoryBannerText, FLinearColor(1.0f, 0.84f, 0.0f, 1.0f), Canvas->ClipY * 0.30f, 3.0f);

	// Subtitle
	DrawCenteredText(TEXT("ALL WAVES CLEARED"), FLinearColor::White, Canvas->ClipY * 0.40f, 1.5f);

	// Final Score
	DrawCenteredText(FString::Printf(TEXT("FINAL SCORE: %d"), Score), FLinearColor(1.0f, 0.85f, 0.1f, 1.0f), Canvas->ClipY * 0.46f, 1.8f);

	// Clear Time
	DrawCenteredText(FormatClearTimeString(ElapsedTime), FLinearColor(0.2f, 0.9f, 0.3f, 1.0f), Canvas->ClipY * 0.52f, 1.3f);

	// Health Remaining
	DrawCenteredText(FormatSurvivingHealthString(CurrentHealth), FLinearColor::White, Canvas->ClipY * 0.57f, 1.2f);

	// Restart Prompt: Press R to Play Again
	DrawCenteredText(RestartPromptVictoryText, FLinearColor(0.4f, 0.9f, 1.0f, 1.0f), Canvas->ClipY * 0.65f, 1.5f);
}
