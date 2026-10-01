// Orb Runner match rules: score, orbs remaining, countdown, win/lose. Pure data + logic, no actors.

#pragma once

#include "CoreMinimal.h"

#include "OrbRules.generated.h"

UENUM(BlueprintType)
enum class EOrbMatchState : uint8
{
	Playing,
	Won,
	Lost
};

USTRUCT(BlueprintType)
struct SHUNYAGAME_API FOrbRules
{
	GENERATED_BODY()

	/** Seconds the player has to collect every orb (Docs/Design/Tuning.md). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rules")
	float TimeLimitSeconds = 60.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Rules")
	int32 Score = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Rules")
	int32 OrbsRemaining = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Rules")
	float TimeRemaining = 60.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Rules")
	EOrbMatchState State = EOrbMatchState::Playing;

	/** Resets score and timer for a match with OrbCount orbs. */
	void Start(int32 OrbCount);

	/** Adds Value to the score and removes one orb; the match is won when none remain. Ignored once over. */
	void CollectOrb(int32 Value);

	/** Advances the countdown; the match is lost when it reaches zero. Ignored once over. */
	void Tick(float DeltaSeconds);

	/** The player has no health left: the match is lost. Ignored once over. */
	void PlayerDied();

	bool IsOver() const { return State != EOrbMatchState::Playing; }
};
