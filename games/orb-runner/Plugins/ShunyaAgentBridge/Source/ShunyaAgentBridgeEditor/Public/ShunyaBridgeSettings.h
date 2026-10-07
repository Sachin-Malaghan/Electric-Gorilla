// Settings for the agent bridge HTTP endpoint ([/Script/ShunyaAgentBridgeEditor.ShunyaBridgeSettings] in DefaultEngine.ini).

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"

#include "ShunyaBridgeSettings.generated.h"

UCLASS(config = Engine, defaultconfig)
class SHUNYAAGENTBRIDGEEDITOR_API UShunyaBridgeSettings : public UObject
{
	GENERATED_BODY()

public:
	/** Localhost port the bridge listens on. */
	UPROPERTY(config)
	int32 Port = 30777;

	/** Shared secret the studio backend must send in the X-Shunya-Token header. */
	UPROPERTY(config)
	FString Token = TEXT("shunya-dev-token");

	UPROPERTY(config)
	bool bEnabled = true;
};
