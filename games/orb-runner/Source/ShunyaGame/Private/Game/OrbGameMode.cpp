// Orb Runner game mode.

#include "Game/OrbGameMode.h"

#include "Kismet/GameplayStatics.h"
#include "Player/OrbRunnerPawn.h"
#include "ShunyaGame.h"
#include "Sound/SoundBase.h"
#include "UI/OrbHUD.h"

AOrbGameMode::AOrbGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	DefaultPawnClass = AOrbRunnerPawn::StaticClass();
	HUDClass = AOrbHUD::StaticClass();
}

void AOrbGameMode::BeginPlay()
{
	// Orbs register in their own BeginPlay, which may run before or after this one,
	// so the count is kept and only the score and timer are reset here.
	const int32 Registered = Rules.OrbsRemaining;
	Rules.Start(Registered);
	Super::BeginPlay();
	PlayCue(TEXT("/Game/Shunya/Audio/S_MusicLoop.S_MusicLoop"));
}

void AOrbGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Rules.Tick(DeltaSeconds);
	CheckMatchEnded();
}

void AOrbGameMode::RegisterOrb()
{
	++Rules.OrbsRemaining;
}

void AOrbGameMode::NotifyOrbCollected(int32 Value)
{
	Rules.CollectOrb(Value);
	CheckMatchEnded();
}

void AOrbGameMode::NotifyPlayerDied()
{
	Rules.PlayerDied();
	CheckMatchEnded();
}

void AOrbGameMode::CheckMatchEnded()
{
	if (bEndAnnounced || !Rules.IsOver())
	{
		return;
	}
	bEndAnnounced = true;
	const bool bWon = Rules.State == EOrbMatchState::Won;
	UE_LOG(LogShunyaGame, Display, TEXT("Orb Runner match over: %s, score %d, %.1fs left"), bWon ? TEXT("WON") : TEXT("LOST"), Rules.Score, Rules.TimeRemaining);
	PlayCue(bWon ? TEXT("/Game/Shunya/Audio/S_Win.S_Win") : TEXT("/Game/Shunya/Audio/S_Lose.S_Lose"));
	OnMatchEnded.Broadcast(Rules.State);
}

void AOrbGameMode::PlayCue(const TCHAR* AssetPath) const
{
	// Audio is authored by the audio department and may not exist yet; the game must run without it.
	if (USoundBase* Sound = LoadObject<USoundBase>(nullptr, AssetPath, nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		UGameplayStatics::PlaySound2D(this, Sound);
	}
}
