// Runtime telemetry for agents.

#include "ShunyaTelemetrySubsystem.h"

#include "Engine/Level.h"
#include "Engine/World.h"
#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, ShunyaAgentBridge);

void UShunyaTelemetrySubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	const float FrameMs = DeltaTime * 1000.f;
	SmoothedFrameMs = Frames == 0 ? FrameMs : FMath::Lerp(SmoothedFrameMs, FrameMs, 0.05f);
	if (Frames > 30) // ignore start-up hitches
	{
		WorstFrameMs = FMath::Max(WorstFrameMs, FrameMs);
	}
	++Frames;
}

TStatId UShunyaTelemetrySubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UShunyaTelemetrySubsystem, STATGROUP_Tickables);
}

bool UShunyaTelemetrySubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

FShunyaTelemetrySnapshot UShunyaTelemetrySubsystem::GetSnapshot() const
{
	FShunyaTelemetrySnapshot Out;
	Out.AverageFrameMs = SmoothedFrameMs;
	Out.AverageFps = SmoothedFrameMs > 0.f ? 1000.f / SmoothedFrameMs : 0.f;
	Out.WorstFrameMs = WorstFrameMs;
	Out.FramesObserved = Frames;
	if (const UWorld* World = GetWorld())
	{
		Out.WorldSeconds = World->GetTimeSeconds();
		if (const ULevel* Level = World->GetCurrentLevel())
		{
			Out.ActorCount = Level->Actors.Num();
		}
	}
	return Out;
}
