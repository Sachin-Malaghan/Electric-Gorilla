// Heads-up display: score, orbs left, time, health, and the end-of-match banner.

#pragma once

#include "CoreMinimal.h"
#include "Game/OrbRules.h"
#include "GameFramework/HUD.h"

#include "OrbHUD.generated.h"

UCLASS()
class SHUNYAGAME_API AOrbHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** "M:SS" with the seconds rounded up, so the clock shows 0:01 until time is really out. */
	static FString FormatTime(float Seconds);

	/** Banner text for a finished match; empty while playing (wording from Docs/Design/Narrative.md). */
	static FString FormatBanner(EOrbMatchState State);

	static FString FormatScoreLine(int32 Score, int32 OrbsRemaining);
};
