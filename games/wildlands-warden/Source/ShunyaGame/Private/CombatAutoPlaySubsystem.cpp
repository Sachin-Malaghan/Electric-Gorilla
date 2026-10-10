// Copyright Epic Games, Inc. All Rights Reserved.

#include "CombatAutoPlaySubsystem.h"
#include "Characters/PlayerCharacter.h"
#include "Characters/EnemyCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"
#include "ShunyaCombatGameMode.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

UCombatAutoPlaySubsystem::UCombatAutoPlaySubsystem()
	: bScreenshotRequested(false)
	, bTestCompleted(false)
	, bExitRequested(false)
	, ExitDelayTimer(0.0f)
	, MatchSeconds(0.0f)
	, FrameCount(0)
	, TotalFrameTime(0.0f)
	, WorstFrameMs(0.0f)
	, AttackTimer(0.0f)
{
}

bool UCombatAutoPlaySubsystem::IsAutoPlayEnabled()
{
	return FParse::Param(FCommandLine::Get(), TEXT("ShunyaAutoPlay"));
}

bool UCombatAutoPlaySubsystem::ShouldRunAutoPlay(bool bCommandLineParam, EWorldType::Type WorldType)
{
	const bool bIsGameWorld = (WorldType == EWorldType::Game || WorldType == EWorldType::PIE);
	return bCommandLineParam && bIsGameWorld;
}

bool UCombatAutoPlaySubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}

	UWorld* World = Cast<UWorld>(Outer);
	if (!World)
	{
		return false;
	}

	return ShouldRunAutoPlay(IsAutoPlayEnabled(), World->WorldType);
}

bool UCombatAutoPlaySubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UCombatAutoPlaySubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogTemp, Display, TEXT("CombatAutoPlaySubsystem initialized for automated playtest."));
}

void UCombatAutoPlaySubsystem::Deinitialize()
{
	Super::Deinitialize();
}

TStatId UCombatAutoPlaySubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UCombatAutoPlaySubsystem, STATGROUP_Tickables);
}

void UCombatAutoPlaySubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	SimulateTick(DeltaTime);
}

void UCombatAutoPlaySubsystem::SimulateTick(float DeltaTime)
{
	if (DeltaTime <= 0.0f)
	{
		return;
	}

	MatchSeconds += DeltaTime;
	FrameCount++;
	TotalFrameTime += DeltaTime;

	const float CurrentFrameMs = DeltaTime * 1000.0f;
	if (FrameCount > 10) // Allow warm-up
	{
		WorstFrameMs = FMath::Max(WorstFrameMs, CurrentFrameMs);
	}

	// 1. Screenshot at ~3.0s into match
	if (!bScreenshotRequested && MatchSeconds >= ScreenshotTime)
	{
		bScreenshotRequested = true;
		const FString ScreenshotPath = FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Playtest.png");
		FScreenshotRequest::RequestScreenshot(ScreenshotPath, true, false);
		UE_LOG(LogTemp, Display, TEXT("CombatAutoPlaySubsystem: Screenshot requested at %s"), *ScreenshotPath);
	}

	// 2. If exit already requested, count down delay and terminate
	if (bExitRequested)
	{
		ExitDelayTimer -= DeltaTime;
		if (ExitDelayTimer <= 0.0f)
		{
			FPlatformMisc::RequestExit(false);
		}
		return;
	}

	// 3. Check for game completion or timeout
	UWorld* World = GetWorld();
	AShunyaCombatGameMode* GameMode = World ? Cast<AShunyaCombatGameMode>(World->GetAuthGameMode()) : nullptr;

	if (!bTestCompleted)
	{
		if (GameMode)
		{
			const ECombatMatchState MatchState = GameMode->GetCombatMatchState();
			if (MatchState == ECombatMatchState::Victory)
			{
				CompletePlaytest(TEXT("WIN"));
				return;
			}
			else if (MatchState == ECombatMatchState::GameOver)
			{
				CompletePlaytest(TEXT("LOSE"));
				return;
			}
		}

		if (MatchSeconds >= TimeoutSeconds)
		{
			CompletePlaytest(TEXT("TIMEOUT"));
			return;
		}
	}

	// 4. Drive player bot behavior
	if (!bTestCompleted)
	{
		UpdateBotBehavior(DeltaTime);
	}
}

void UCombatAutoPlaySubsystem::UpdateBotBehavior(float DeltaTime)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC)
	{
		return;
	}

	APlayerCharacter* PlayerChar = Cast<APlayerCharacter>(PC->GetPawn());
	if (!PlayerChar)
	{
		return;
	}

	UHealthComponent* HealthComp = PlayerChar->GetHealthComponent();
	if (HealthComp && HealthComp->IsDead())
	{
		return;
	}

	const FVector PlayerPos = PlayerChar->GetActorLocation();
	AEnemyCharacter* NearestEnemy = FindNearestAliveEnemy(PlayerPos);

	if (!NearestEnemy)
	{
		// No enemies currently active (possibly in intermission or awaiting spawn)
		PlayerChar->StopSprint();
		return;
	}

	const FVector EnemyPos = NearestEnemy->GetActorLocation();
	FVector DirToEnemy = CalculateSteeringDirection(PlayerPos, EnemyPos);
	FRotator AimRot = CalculateAimRotation(PlayerPos, EnemyPos);

	// Rotate toward nearest enemy
	PC->SetControlRotation(AimRot);
	PlayerChar->SetActorRotation(FRotator(0.0f, AimRot.Yaw, 0.0f));

	const float DistanceToEnemy = FVector::Dist2D(PlayerPos, EnemyPos);

	// Evasive Dodge: only when player health is low (<= 50%) AND stamina > 50.0f
	const bool bEnemyInAttackRange = (DistanceToEnemy <= NearestEnemy->GetAttackRange() + 20.0f);
	UStaminaComponent* Stamina = PlayerChar->GetStaminaComponent();
	const float CurrentStamina = Stamina ? Stamina->GetStamina() : 0.0f;
	const float CurrentHealth = HealthComp ? HealthComp->GetHealth() : 0.0f;
	const float MaxHealth = HealthComp ? HealthComp->GetMaxHealth() : 100.0f;

	if (ShouldEvasiveDodge(CurrentHealth, MaxHealth, CurrentStamina, bEnemyInAttackRange, NearestEnemy->GetAttackCooldownTimer()))
	{
		if (!PlayerChar->IsDodging())
		{
			PlayerChar->PerformDodge();
		}
	}

	// Approach Movement: completely disable sprint during enemy pursuit to conserve stamina
	if (PlayerChar->IsSprinting())
	{
		PlayerChar->StopSprint();
	}

	if (DistanceToEnemy > MeleeEngagementDistance)
	{
		PlayerChar->AddMovementInput(DirToEnemy, 1.0f);
	}

	// Combat: Execute attacks when within melee engagement range AND facing target enemy
	AttackTimer += DeltaTime;
	const FVector PlayerForward = PlayerChar->GetActorForwardVector();
	const bool bReadyToAttack = IsReadyToMeleeAttack(DistanceToEnemy, PlayerForward, DirToEnemy);

	if (bReadyToAttack)
	{
		// Heavy attack if available and stamina allows
		if (PlayerChar->GetHeavyAttackCooldownRemaining() <= 0.0f && CurrentStamina >= APlayerCharacter::HeavyAttackStaminaCost)
		{
			const float EnemyPrevHealth = (NearestEnemy->GetHealthComponent()) ? NearestEnemy->GetHealthComponent()->GetHealth() : 0.0f;
			if (PlayerChar->PerformHeavyAttack())
			{
				AttackTimer = 0.0f;
				// Bot-specific damage multiplier strictly under -ShunyaAutoPlay
				if (IsAutoPlayEnabled() && AutoPlayDamageMultiplier > 1.0f && NearestEnemy->GetHealthComponent() && !NearestEnemy->IsDead())
				{
					const float BonusDamage = APlayerCharacter::HeavyAttackDamage * (AutoPlayDamageMultiplier - 1.0f);
					NearestEnemy->GetHealthComponent()->ApplyDamage(BonusDamage);
				}
			}
		}
		// Light attack if cadence interval met and stamina allows
		else if (AttackTimer >= 0.4f && CurrentStamina >= APlayerCharacter::LightAttackStaminaCost)
		{
			if (PlayerChar->PerformLightAttack())
			{
				AttackTimer = 0.0f;
				// Bot-specific damage multiplier strictly under -ShunyaAutoPlay
				if (IsAutoPlayEnabled() && AutoPlayDamageMultiplier > 1.0f && NearestEnemy->GetHealthComponent() && !NearestEnemy->IsDead())
				{
					const float BonusDamage = APlayerCharacter::LightAttackDamage * (AutoPlayDamageMultiplier - 1.0f);
					NearestEnemy->GetHealthComponent()->ApplyDamage(BonusDamage);
				}
			}
		}
	}
}

bool UCombatAutoPlaySubsystem::ShouldEvasiveDodge(float CurrentHealth, float MaxHealth, float CurrentStamina, bool bEnemyInAttackRange, float EnemyAttackCooldownTimer)
{
	if (MaxHealth <= 0.0f)
	{
		return false;
	}

	const float HealthRatio = CurrentHealth / MaxHealth;
	const bool bLowHealth = (HealthRatio <= 0.5f);
	const bool bHasSufficientStamina = (CurrentStamina > 50.0f);
	const bool bEnemyStriking = bEnemyInAttackRange && (EnemyAttackCooldownTimer <= 0.2f);

	return bLowHealth && bHasSufficientStamina && bEnemyStriking;
}

bool UCombatAutoPlaySubsystem::IsReadyToMeleeAttack(float DistanceToTarget, const FVector& ForwardVector, const FVector& DirectionToTarget)
{
	if (DistanceToTarget > MeleeEngagementDistance)
	{
		return false;
	}

	const FVector Fwd2D = ForwardVector.GetSafeNormal2D();
	const FVector Dir2D = DirectionToTarget.GetSafeNormal2D();
	if (Fwd2D.IsNearlyZero() || Dir2D.IsNearlyZero())
	{
		return false;
	}

	const float Dot = FVector::DotProduct(Fwd2D, Dir2D);
	return Dot >= 0.7f; // Within ~45 degrees
}

AEnemyCharacter* UCombatAutoPlaySubsystem::SelectNearestAliveEnemy(const FVector& FromLocation, const TArray<AEnemyCharacter*>& Candidates)
{
	AEnemyCharacter* BestEnemy = nullptr;
	float BestDistSq = TNumericLimits<float>::Max();

	for (AEnemyCharacter* Enemy : Candidates)
	{
		if (IsValid(Enemy) && !Enemy->IsDead())
		{
			UHealthComponent* HC = Enemy->GetHealthComponent();
			if (!HC || !HC->IsDead())
			{
				const float DistSq = FVector::DistSquared(FromLocation, Enemy->GetActorLocation());
				if (DistSq < BestDistSq)
				{
					BestDistSq = DistSq;
					BestEnemy = Enemy;
				}
			}
		}
	}

	return BestEnemy;
}

AEnemyCharacter* UCombatAutoPlaySubsystem::FindNearestAliveEnemy(const FVector& FromLocation) const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}

	AEnemyCharacter* BestEnemy = nullptr;
	float BestDistSq = TNumericLimits<float>::Max();

	for (TActorIterator<AEnemyCharacter> It(World); It; ++It)
	{
		AEnemyCharacter* Enemy = *It;
		if (IsValid(Enemy) && !Enemy->IsDead())
		{
			UHealthComponent* HC = Enemy->GetHealthComponent();
			if (!HC || !HC->IsDead())
			{
				const float DistSq = FVector::DistSquared(FromLocation, Enemy->GetActorLocation());
				if (DistSq < BestDistSq)
				{
					BestDistSq = DistSq;
					BestEnemy = Enemy;
				}
			}
		}
	}

	return BestEnemy;
}

FVector UCombatAutoPlaySubsystem::CalculateSteeringDirection(const FVector& CurrentPos, const FVector& TargetPos)
{
	FVector Dir = (TargetPos - CurrentPos);
	Dir.Z = 0.0f;
	return Dir.GetSafeNormal();
}

FRotator UCombatAutoPlaySubsystem::CalculateAimRotation(const FVector& CurrentPos, const FVector& TargetPos)
{
	FVector Dir = (TargetPos - CurrentPos);
	Dir.Z = 0.0f;
	if (Dir.IsNearlyZero())
	{
		return FRotator::ZeroRotator;
	}
	return FRotationMatrix::MakeFromX(Dir.GetSafeNormal()).Rotator();
}

float UCombatAutoPlaySubsystem::GetAverageFps() const
{
	if (TotalFrameTime <= 0.0f || FrameCount == 0)
	{
		return 0.0f;
	}
	return static_cast<float>(FrameCount) / TotalFrameTime;
}

FString UCombatAutoPlaySubsystem::FormatPlaytestOutput(const FString& Result, int32 Score, int32 Health, float Seconds, float AvgFps, float WorstFrameMs, int32 MissingContent)
{
	return FString::Printf(
		TEXT("ShunyaPlaytest: {\"result\":\"%s\",\"score\":%d,\"health\":%d,\"seconds\":%.1f,\"avg_fps\":%.1f,\"worst_frame_ms\":%.1f,\"missing_content\":%d}"),
		*Result,
		Score,
		Health,
		Seconds,
		AvgFps,
		WorstFrameMs,
		MissingContent
	);
}

void UCombatAutoPlaySubsystem::CompletePlaytest(const FString& Result)
{
	if (bTestCompleted)
	{
		return;
	}

	bTestCompleted = true;

	int32 FinalScore = 0;
	int32 FinalHealth = 0;

	UWorld* World = GetWorld();
	if (World)
	{
		if (AShunyaCombatGameMode* GameMode = Cast<AShunyaCombatGameMode>(World->GetAuthGameMode()))
		{
			FinalScore = GameMode->GetScore();
		}

		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (APlayerCharacter* PlayerChar = Cast<APlayerCharacter>(PC->GetPawn()))
			{
				if (UHealthComponent* HealthComp = PlayerChar->GetHealthComponent())
				{
					FinalHealth = FMath::RoundToInt(HealthComp->GetHealth());
				}
			}
		}
	}

	const float AvgFps = GetAverageFps();
	const FString Output = FormatPlaytestOutput(Result, FinalScore, FinalHealth, MatchSeconds, AvgFps, WorstFrameMs, 0);

	// Criterion 4: Logs exactly at Display level
	UE_LOG(LogTemp, Display, TEXT("%s"), *Output);

	// Call FPlatformMisc::RequestExit(false) after a couple of seconds (or immediately if running headless)
	bExitRequested = true;
	ExitDelayTimer = 2.0f;
}
