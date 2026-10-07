// QA autoplay bot and playtest report.

#include "Tools/OrbPlaytestSubsystem.h"

#include "AI/ChaserDrone.h"
#include "Components/HealthComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Game/OrbGameMode.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "Pickups/OrbCollectible.h"
#include "Player/OrbRunnerPawn.h"
#include "ShunyaGame.h"
#include "UnrealClient.h"

namespace OrbPlaytest
{
	const float ScreenshotAtSeconds = 4.f;
	const float GiveUpAfterSeconds = 90.f;
	const float ExitDelaySeconds = 2.f;
	const float AvoidRadius = 420.f;

	// Everything the game looks up by path at runtime. A build that lacks any of these still runs
	// (the code tolerates missing content), so the playtest reports them explicitly.
	const TCHAR* RuntimeContent[] = {
		TEXT("/Game/Shunya/Characters/M_Player.M_Player"), TEXT("/Game/Shunya/Characters/M_Drone.M_Drone"), TEXT("/Game/Shunya/Props/M_Orb.M_Orb"),
		TEXT("/Game/Shunya/Audio/S_Pickup.S_Pickup"), TEXT("/Game/Shunya/Audio/S_Hit.S_Hit"), TEXT("/Game/Shunya/Audio/S_Win.S_Win"),
		TEXT("/Game/Shunya/Audio/S_Lose.S_Lose"), TEXT("/Game/Shunya/Audio/S_MusicLoop.S_MusicLoop"),
	};
}

bool UOrbPlaytestSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	return FParse::Param(FCommandLine::Get(), TEXT("ShunyaAutoPlay")) && Super::ShouldCreateSubsystem(Outer);
}

bool UOrbPlaytestSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId UOrbPlaytestSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UOrbPlaytestSubsystem, STATGROUP_Tickables);
}

void UOrbPlaytestSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	UWorld* World = GetWorld();
	const AOrbGameMode* GameMode = World ? World->GetAuthGameMode<AOrbGameMode>() : nullptr;
	AOrbRunnerPawn* Player = World ? Cast<AOrbRunnerPawn>(UGameplayStatics::GetPlayerPawn(World, 0)) : nullptr;
	if (!GameMode || !Player)
	{
		return; // not an Orb Runner level, or the player has not spawned yet
	}

	Elapsed += DeltaTime;
	if (Elapsed > 1.f) // ignore start-up hitches in the frame statistics
	{
		++Frames;
		WorstFrameMs = FMath::Max(WorstFrameMs, DeltaTime * 1000.f);
	}

	if (!bScreenshotRequested && Elapsed >= OrbPlaytest::ScreenshotAtSeconds)
	{
		bScreenshotRequested = true;
		FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Playtest.png"), /*bShowUI*/ true, /*bAddUniqueSuffix*/ false);
	}

	if (bReported)
	{
		if (Elapsed - FinishedAt >= OrbPlaytest::ExitDelaySeconds)
		{
			FPlatformMisc::RequestExit(false);
		}
		return;
	}

	if (GameMode->GetRules().IsOver())
	{
		Report(GameMode->GetRules().State == EOrbMatchState::Won ? TEXT("WIN") : TEXT("LOSE"));
		return;
	}
	if (Elapsed >= OrbPlaytest::GiveUpAfterSeconds)
	{
		Report(TEXT("TIMEOUT"));
		return;
	}

	TArray<FVector> Orbs;
	for (TActorIterator<AOrbCollectible> It(World); It; ++It)
	{
		Orbs.Add(It->GetActorLocation());
	}
	const FVector From = Player->GetActorLocation();
	const int32 Nearest = PickNearest(From, Orbs);
	FVector Threat = From + FVector(1.e6f, 0.f, 0.f);
	for (TActorIterator<AChaserDrone> It(World); It; ++It)
	{
		if (FVector::DistSquared2D(It->GetActorLocation(), From) < FVector::DistSquared2D(Threat, From))
		{
			Threat = It->GetActorLocation();
		}
	}
	Player->SetExternalMoveInput(Nearest == INDEX_NONE ? FVector2D::ZeroVector : ComputeBotInput(From, Orbs[Nearest], Threat, OrbPlaytest::AvoidRadius));
}

void UOrbPlaytestSubsystem::Report(const TCHAR* Result)
{
	bReported = true;
	FinishedAt = Elapsed;
	const UWorld* World = GetWorld();
	const AOrbGameMode* GameMode = World->GetAuthGameMode<AOrbGameMode>();
	const AOrbRunnerPawn* Player = Cast<AOrbRunnerPawn>(UGameplayStatics::GetPlayerPawn(World, 0));
	const FOrbRules& Rules = GameMode->GetRules();
	const float MeasuredSeconds = FMath::Max(Elapsed - 1.f, 0.001f);
	int32 MissingContent = 0;
	for (const TCHAR* Path : OrbPlaytest::RuntimeContent)
	{
		if (!LoadObject<UObject>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			++MissingContent;
			UE_LOG(LogShunyaGame, Warning, TEXT("ShunyaPlaytest missing content: %s"), Path);
		}
	}
	UE_LOG(LogShunyaGame, Display,
		TEXT("ShunyaPlaytest: {\"result\":\"%s\",\"score\":%d,\"orbs_remaining\":%d,\"time_remaining\":%.1f,\"health\":%.0f,\"seconds\":%.1f,\"avg_fps\":%.1f,\"worst_frame_ms\":%.1f,\"missing_content\":%d,\"map\":\"%s\"}"),
		Result, Rules.Score, Rules.OrbsRemaining, Rules.TimeRemaining, Player && Player->GetHealth() ? Player->GetHealth()->GetHealth() : 0.f,
		Elapsed, Frames / MeasuredSeconds, WorstFrameMs, MissingContent, *World->GetMapName());
}

int32 UOrbPlaytestSubsystem::PickNearest(const FVector& From, const TArray<FVector>& Candidates)
{
	int32 Best = INDEX_NONE;
	double BestDistance = TNumericLimits<double>::Max();
	for (int32 Index = 0; Index < Candidates.Num(); ++Index)
	{
		const double Distance = FVector::DistSquared2D(From, Candidates[Index]);
		if (Distance < BestDistance)
		{
			BestDistance = Distance;
			Best = Index;
		}
	}
	return Best;
}

FVector2D UOrbPlaytestSubsystem::ComputeBotInput(const FVector& From, const FVector& Target, const FVector& Threat, float AvoidRadius)
{
	FVector2D Direction = FVector2D(Target - From).GetSafeNormal();
	const FVector2D FromThreat = FVector2D(From - Threat);
	const double ThreatDistance = FromThreat.Size();
	if (AvoidRadius > 0.f && ThreatDistance < AvoidRadius)
	{
		// the closer the threat, the more the bot steers away from it
		Direction += FromThreat.GetSafeNormal() * (1.5 * (1.0 - ThreatDistance / AvoidRadius));
	}
	return Direction.GetSafeNormal();
}
