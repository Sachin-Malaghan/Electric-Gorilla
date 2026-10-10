// Copyright Epic Games, Inc. All Rights Reserved.

#include "ShunyaCombatTypes.h"

FWaveCombatRules::FWaveCombatRules()
	: MatchState(ECombatMatchState::NotStarted)
	, CurrentWave(0)
	, ActiveEnemies(0)
	, TotalEnemiesSpawnedInWave(0)
	, TotalEnemiesDefeated(0)
	, Score(0)
	, ElapsedTime(0.0f)
	, InterWaveCountdown(0.0f)
	, bInIntermission(false)
	, bWaveInProgress(false)
{
}

void FWaveCombatRules::StartMatch()
{
	ResetMatch();
	MatchState = ECombatMatchState::InProgress;
	StartWave(1);
}

void FWaveCombatRules::ResetMatch()
{
	MatchState = ECombatMatchState::NotStarted;
	CurrentWave = 0;
	ActiveEnemies = 0;
	TotalEnemiesSpawnedInWave = 0;
	TotalEnemiesDefeated = 0;
	Score = 0;
	ElapsedTime = 0.0f;
	InterWaveCountdown = 0.0f;
	bInIntermission = false;
	bWaveInProgress = false;
}

bool FWaveCombatRules::StartWave(int32 WaveIndex)
{
	if (WaveIndex < 1 || WaveIndex > TotalWaves)
	{
		return false;
	}

	CurrentWave = WaveIndex;
	FWaveDefinition Def = GetWaveDefinition(CurrentWave);
	ActiveEnemies = Def.EnemyCount;
	TotalEnemiesSpawnedInWave = 0;
	bInIntermission = false;
	bWaveInProgress = true;
	InterWaveCountdown = 0.0f;
	return true;
}

void FWaveCombatRules::RecordEnemyKill()
{
	if (MatchState != ECombatMatchState::InProgress)
	{
		return;
	}

	if (ActiveEnemies > 0)
	{
		ActiveEnemies--;
	}
	TotalEnemiesDefeated++;
	Score += BaseKillScore;

	// Check wave clear
	if (ActiveEnemies == 0)
	{
		bWaveInProgress = false;

		if (CurrentWave >= TotalWaves)
		{
			// All 3 waves cleared!
			MatchState = ECombatMatchState::Victory;
		}
		else
		{
			// Inter-wave delay
			bInIntermission = true;
			FWaveDefinition Def = GetWaveDefinition(CurrentWave);
			InterWaveCountdown = Def.InterWaveDelay;
		}
	}
}

void FWaveCombatRules::HandlePlayerDeath()
{
	if (MatchState == ECombatMatchState::InProgress)
	{
		MatchState = ECombatMatchState::GameOver;
		bWaveInProgress = false;
		bInIntermission = false;
	}
}

void FWaveCombatRules::AdvanceTime(float DeltaTime)
{
	if (DeltaTime <= 0.0f)
	{
		return;
	}

	if (MatchState == ECombatMatchState::InProgress)
	{
		ElapsedTime += DeltaTime;

		if (bInIntermission)
		{
			InterWaveCountdown -= DeltaTime;
			if (InterWaveCountdown <= 0.0f)
			{
				InterWaveCountdown = 0.0f;
				bInIntermission = false;
				StartWave(CurrentWave + 1);
			}
		}
	}
}

FWaveDefinition FWaveCombatRules::GetWaveDefinition(int32 WaveNumber)
{
	FWaveDefinition Def;
	Def.WaveNumber = WaveNumber;

	switch (WaveNumber)
	{
	case 1:
		Def.EnemyCount = 3;
		Def.HealthMultiplier = 1.0f;
		Def.EnemyHealth = 50.0f;
		Def.InterWaveDelay = 3.0f;
		break;
	case 2:
		Def.EnemyCount = 5;
		Def.HealthMultiplier = 1.0f;
		Def.EnemyHealth = 50.0f;
		Def.InterWaveDelay = 3.0f;
		break;
	case 3:
		Def.EnemyCount = 8;
		Def.HealthMultiplier = 1.25f;
		Def.EnemyHealth = 62.5f;
		Def.InterWaveDelay = 0.0f;
		break;
	default:
		Def.EnemyCount = 0;
		Def.HealthMultiplier = 1.0f;
		Def.EnemyHealth = 50.0f;
		Def.InterWaveDelay = 0.0f;
		break;
	}

	return Def;
}

TArray<FVector> FWaveCombatRules::CalculateSpawnLocations(int32 WaveNumber, float Radius, const FVector& Center)
{
	TArray<FVector> Locations;
	FWaveDefinition Def = GetWaveDefinition(WaveNumber);
	const int32 Count = Def.EnemyCount;
	if (Count <= 0)
	{
		return Locations;
	}

	Locations.Reserve(Count);
	const float AngleStep = 360.0f / static_cast<float>(Count);

	for (int32 i = 0; i < Count; ++i)
	{
		const float AngleDeg = static_cast<float>(i) * AngleStep;
		const float AngleRad = FMath::DegreesToRadians(AngleDeg);

		const float X = Center.X + Radius * FMath::Cos(AngleRad);
		const float Y = Center.Y + Radius * FMath::Sin(AngleRad);
		const float Z = Center.Z;

		Locations.Add(FVector(X, Y, Z));
	}

	return Locations;
}

bool FWaveCombatRules::IsWaveCleared() const
{
	return ActiveEnemies == 0;
}
