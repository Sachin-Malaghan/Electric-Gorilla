// Copyright Epic Games, Inc. All Rights Reserved.

#include "ShunyaCombatGameMode.h"
#include "SHUDCombatHUD.h"
#include "Characters/EnemyCharacter.h"
#include "Characters/PlayerCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/World.h"

AShunyaCombatGameMode::AShunyaCombatGameMode()
	: SpawnRadius(1200.0f)
	, SpawnStaggerDelay(0.5f)
	, SpawnTimer(0.0f)
	, CurrentWaveHealthMultiplier(1.0f)
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	DefaultPawnClass = APlayerCharacter::StaticClass();
	HUDClass = ASHUDCombatHUD::StaticClass();
	EnemyClass = AEnemyCharacter::StaticClass();
}

void AShunyaCombatGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);
}

void AShunyaCombatGameMode::StartPlay()
{
	Super::StartPlay();

	BindPlayerDeathListener();
	StartMatch();
}

void AShunyaCombatGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (CombatRules.MatchState != ECombatMatchState::InProgress)
	{
		return;
	}

	int32 PrevWave = CombatRules.CurrentWave;
	bool bWasIntermission = CombatRules.bInIntermission;

	CombatRules.AdvanceTime(DeltaSeconds);

	// If intermission finished and new wave started
	if (bWasIntermission && !CombatRules.bInIntermission && CombatRules.CurrentWave > PrevWave)
	{
		BeginWave(CombatRules.CurrentWave);
	}

	ProcessSpawnQueue(DeltaSeconds);
}

void AShunyaCombatGameMode::StartMatch()
{
	ClearAllEnemies();
	CombatRules.StartMatch();
	TransitionMatchState(ECombatMatchState::InProgress);
	BeginWave(1);
}

void AShunyaCombatGameMode::RestartMatch()
{
	// Reset Player position and vitals
	if (UWorld* World = GetWorld())
	{
		APlayerController* PC = World->GetFirstPlayerController();
		if (PC)
		{
			APawn* Pawn = PC->GetPawn();
			if (APlayerCharacter* PlayerChar = Cast<APlayerCharacter>(Pawn))
			{
				if (UHealthComponent* HC = PlayerChar->GetHealthComponent())
				{
					HC->SetMaxHealth(100.0f, true);
				}
				if (UStaminaComponent* SC = PlayerChar->GetStaminaComponent())
				{
					SC->RestoreStamina(100.0f);
				}
				PlayerChar->SetActorLocation(FVector(0.0f, 0.0f, 100.0f));
				PlayerChar->SetActorRotation(FRotator::ZeroRotator);
			}
		}
	}

	BindPlayerDeathListener();
	StartMatch();
}

void AShunyaCombatGameMode::BeginWave(int32 WaveNumber)
{
	CombatRules.StartWave(WaveNumber);
	FWaveDefinition Def = FWaveCombatRules::GetWaveDefinition(WaveNumber);
	CurrentWaveHealthMultiplier = Def.HealthMultiplier;

	SpawnEnemiesForCurrentWave();
	OnWaveStarted.Broadcast(WaveNumber);
}

void AShunyaCombatGameMode::SpawnEnemiesForCurrentWave()
{
	PendingSpawnQueue.Empty();
	SpawnTimer = 0.0f;

	TArray<FVector> SpawnPoints = FWaveCombatRules::CalculateSpawnLocations(CombatRules.CurrentWave, SpawnRadius);
	for (const FVector& Loc : SpawnPoints)
	{
		// Spawn orientation looking at center
		FRotator Rot = (-Loc).Rotation();
		Rot.Pitch = 0.0f;
		Rot.Roll = 0.0f;
		PendingSpawnQueue.Add(FTransform(Rot, Loc));
	}
}

void AShunyaCombatGameMode::ProcessSpawnQueue(float DeltaTime)
{
	if (PendingSpawnQueue.Num() == 0)
	{
		return;
	}

	SpawnTimer -= DeltaTime;
	if (SpawnTimer <= 0.0f)
	{
		SpawnTimer = SpawnStaggerDelay;
		FTransform SpawnTransform = PendingSpawnQueue[0];
		PendingSpawnQueue.RemoveAt(0);

		UWorld* World = GetWorld();
		if (!World || !EnemyClass)
		{
			return;
		}

		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

		AEnemyCharacter* Enemy = World->SpawnActor<AEnemyCharacter>(EnemyClass, SpawnTransform, SpawnParams);
		if (Enemy)
		{
			if (UHealthComponent* HC = Enemy->GetHealthComponent())
			{
				float AdjustedHealth = 50.0f * CurrentWaveHealthMultiplier;
				HC->SetMaxHealth(AdjustedHealth, true);
				HC->OnDeath.AddDynamic(this, &AShunyaCombatGameMode::OnEnemyKilled);
			}

			// Target player if exists
			APlayerController* PC = World->GetFirstPlayerController();
			if (PC && PC->GetPawn())
			{
				Enemy->TargetActor = PC->GetPawn();
			}

			SpawnedEnemies.Add(Enemy);
		}
	}
}

void AShunyaCombatGameMode::OnEnemyKilled(AActor* DeadActor)
{
	int32 PrevScore = CombatRules.Score;
	int32 PrevWave = CombatRules.CurrentWave;
	ECombatMatchState PrevState = CombatRules.MatchState;

	CombatRules.RecordEnemyKill();

	int32 ScoreDelta = CombatRules.Score - PrevScore;
	if (ScoreDelta > 0)
	{
		OnScoreChanged.Broadcast(CombatRules.Score, ScoreDelta);
	}

	if (CombatRules.IsWaveCleared())
	{
		OnWaveCleared.Broadcast(PrevWave);
	}

	if (CombatRules.MatchState != PrevState)
	{
		TransitionMatchState(CombatRules.MatchState);
	}
}

void AShunyaCombatGameMode::OnPlayerKilled(AActor* DeadActor)
{
	if (CombatRules.MatchState == ECombatMatchState::InProgress)
	{
		CombatRules.HandlePlayerDeath();
		TransitionMatchState(ECombatMatchState::GameOver);
	}
}

void AShunyaCombatGameMode::ClearAllEnemies()
{
	PendingSpawnQueue.Empty();

	for (TWeakObjectPtr<AEnemyCharacter> WeakEnemy : SpawnedEnemies)
	{
		if (WeakEnemy.IsValid())
		{
			WeakEnemy->Destroy();
		}
	}
	SpawnedEnemies.Empty();
}

void AShunyaCombatGameMode::TransitionMatchState(ECombatMatchState NewState)
{
	OnMatchStateChanged.Broadcast(NewState);

	if (NewState == ECombatMatchState::GameOver || NewState == ECombatMatchState::Victory)
	{
		PendingSpawnQueue.Empty();
	}
}

void AShunyaCombatGameMode::BindPlayerDeathListener()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (PC && PC->GetPawn())
	{
		if (APlayerCharacter* PlayerChar = Cast<APlayerCharacter>(PC->GetPawn()))
		{
			if (UHealthComponent* HC = PlayerChar->GetHealthComponent())
			{
				HC->OnDeath.RemoveAll(this);
				HC->OnDeathNative.RemoveAll(this);
				HC->OnDeath.AddDynamic(this, &AShunyaCombatGameMode::OnPlayerKilled);
			}
		}
	}
}
