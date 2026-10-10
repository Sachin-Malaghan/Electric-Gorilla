// Runtime telemetry for agents (spec 17/18: runtime API). Exists only in game / PIE worlds.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"

#include "ShunyaTelemetrySubsystem.generated.h"

USTRUCT()
struct SHUNYAAGENTBRIDGE_API FShunyaTelemetrySnapshot
{
	GENERATED_BODY()

	UPROPERTY()
	float AverageFrameMs = 0.f;

	UPROPERTY()
	float AverageFps = 0.f;

	UPROPERTY()
	float WorstFrameMs = 0.f;

	UPROPERTY()
	int64 FramesObserved = 0;

	UPROPERTY()
	float WorldSeconds = 0.f;

	UPROPERTY()
	int32 ActorCount = 0;
};

UCLASS()
class SHUNYAAGENTBRIDGE_API UShunyaTelemetrySubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

	FShunyaTelemetrySnapshot GetSnapshot() const;

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	float SmoothedFrameMs = 0.f;
	float WorstFrameMs = 0.f;
	int64 Frames = 0;
};
