// QA tooling: with -ShunyaAutoPlay on the command line, a bot plays the match, a screenshot is
// captured, the result and frame rate are logged as one "ShunyaPlaytest:" JSON line, and the game exits.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"

#include "OrbPlaytestSubsystem.generated.h"

UCLASS()
class SHUNYAGAME_API UOrbPlaytestSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	/** Index of the candidate closest to From on the ground plane, or INDEX_NONE when there are none. */
	static int32 PickNearest(const FVector& From, const TArray<FVector>& Candidates);

	/** Direction to move: toward Target, pushed away from Threat when it is within AvoidRadius. Unit length or zero. */
	static FVector2D ComputeBotInput(const FVector& From, const FVector& Target, const FVector& Threat, float AvoidRadius);

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	void Report(const TCHAR* Result);

	float Elapsed = 0.f;
	float FinishedAt = -1.f;
	int64 Frames = 0;
	float WorstFrameMs = 0.f;
	bool bScreenshotRequested = false;
	bool bReported = false;
};
