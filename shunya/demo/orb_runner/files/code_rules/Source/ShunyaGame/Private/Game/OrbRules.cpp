// Orb Runner match rules.

#include "Game/OrbRules.h"

void FOrbRules::Start(int32 OrbCount)
{
	Score = 0;
	OrbsRemaining = FMath::Max(0, OrbCount);
	TimeRemaining = TimeLimitSeconds;
	State = EOrbMatchState::Playing;
}

void FOrbRules::CollectOrb(int32 Value)
{
	if (IsOver() || OrbsRemaining <= 0)
	{
		return;
	}
	Score += FMath::Max(0, Value);
	--OrbsRemaining;
	if (OrbsRemaining == 0)
	{
		State = EOrbMatchState::Won;
	}
}

void FOrbRules::Tick(float DeltaSeconds)
{
	if (IsOver() || DeltaSeconds <= 0.f)
	{
		return;
	}
	TimeRemaining = FMath::Max(0.f, TimeRemaining - DeltaSeconds);
	if (TimeRemaining <= 0.f)
	{
		State = EOrbMatchState::Lost;
	}
}

void FOrbRules::PlayerDied()
{
	if (!IsOver())
	{
		State = EOrbMatchState::Lost;
	}
}
