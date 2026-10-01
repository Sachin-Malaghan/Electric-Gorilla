// Heads-up display.

#include "UI/OrbHUD.h"

#include "Components/HealthComponent.h"
#include "Engine/Canvas.h"
#include "Game/OrbGameMode.h"
#include "Kismet/GameplayStatics.h"
#include "Player/OrbRunnerPawn.h"

void AOrbHUD::DrawHUD()
{
	Super::DrawHUD();
	const AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr;
	if (!GameMode || !Canvas)
	{
		return;
	}
	const FOrbRules& Rules = GameMode->GetRules();
	const FLinearColor Cyan(0.3f, 0.95f, 1.f);
	const FLinearColor Amber(1.f, 0.75f, 0.2f);
	const FLinearColor Red(1.f, 0.3f, 0.3f);

	DrawText(FormatScoreLine(Rules.Score, Rules.OrbsRemaining), Cyan, 40.f, 30.f, nullptr, 2.f);
	DrawText(FString::Printf(TEXT("TIME %s"), *FormatTime(Rules.TimeRemaining)), Rules.TimeRemaining < 10.f ? Red : Amber, 40.f, 70.f, nullptr, 2.f);

	if (const AOrbRunnerPawn* Player = Cast<AOrbRunnerPawn>(UGameplayStatics::GetPlayerPawn(this, 0)))
	{
		if (const UHealthComponent* Health = Player->GetHealth())
		{
			const float Fraction = Health->GetMaxHealth() > 0.f ? Health->GetHealth() / Health->GetMaxHealth() : 0.f;
			DrawText(TEXT("HULL"), FLinearColor::White, 40.f, 112.f, nullptr, 1.6f);
			DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.5f), 120.f, 116.f, 240.f, 18.f);
			DrawRect(Fraction > 0.3f ? Cyan : Red, 120.f, 116.f, 240.f * FMath::Clamp(Fraction, 0.f, 1.f), 18.f);
		}
	}

	const FString Banner = FormatBanner(Rules.State);
	if (!Banner.IsEmpty())
	{
		float Width = 0.f, Height = 0.f;
		GetTextSize(Banner, Width, Height, nullptr, 4.f);
		DrawText(Banner, Rules.State == EOrbMatchState::Won ? Cyan : Red, (Canvas->SizeX - Width) * 0.5f, Canvas->SizeY * 0.4f, nullptr, 4.f);
	}
}

FString AOrbHUD::FormatTime(float Seconds)
{
	const int32 Whole = FMath::Max(0, FMath::CeilToInt(Seconds));
	return FString::Printf(TEXT("%d:%02d"), Whole / 60, Whole % 60);
}

FString AOrbHUD::FormatBanner(EOrbMatchState State)
{
	switch (State)
	{
	case EOrbMatchState::Won:
		return TEXT("ALL ORBS RECOVERED");
	case EOrbMatchState::Lost:
		return TEXT("SIGNAL LOST");
	default:
		return FString();
	}
}

FString AOrbHUD::FormatScoreLine(int32 Score, int32 OrbsRemaining)
{
	return FString::Printf(TEXT("SCORE %d   ORBS LEFT %d"), Score, OrbsRemaining);
}
