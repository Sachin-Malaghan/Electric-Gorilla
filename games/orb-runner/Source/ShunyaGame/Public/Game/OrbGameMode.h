// Orb Runner game mode: owns the match rules and announces the result.

#pragma once

#include "CoreMinimal.h"
#include "Game/OrbRules.h"
#include "GameFramework/GameModeBase.h"

#include "OrbGameMode.generated.h"

DECLARE_MULTICAST_DELEGATE_OneParam(FOnOrbMatchEnded, EOrbMatchState);

UCLASS()
class SHUNYAGAME_API AOrbGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AOrbGameMode();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Orbs call this from BeginPlay so the match knows how many there are. */
	void RegisterOrb();

	void NotifyOrbCollected(int32 Value);
	void NotifyPlayerDied();

	const FOrbRules& GetRules() const { return Rules; }

	FOnOrbMatchEnded OnMatchEnded;

protected:
	UPROPERTY(EditDefaultsOnly, Category = "Rules")
	FOrbRules Rules;

private:
	void CheckMatchEnded();
	void PlayCue(const TCHAR* AssetPath) const;

	bool bEndAnnounced = false;
};
