// Procedural idle animation for pickups: spins the owner around Z and bobs it up and down.

#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"

#include "SpinBobComponent.generated.h"

UCLASS(ClassGroup = (Shunya), meta = (BlueprintSpawnableComponent))
class SHUNYAGAME_API USpinBobComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	USpinBobComponent();

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Vertical offset at Time for a sine bob: 0 at Time 0, +Amplitude a quarter cycle later. */
	static float ComputeBobOffset(float Time, float Amplitude, float CyclesPerSecond);

	/** Yaw in [0, 360) after spinning for Time seconds. */
	static float ComputeYaw(float Time, float DegreesPerSecond);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Animation")
	float SpinDegreesPerSecond = 90.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Animation")
	float BobAmplitude = 18.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Animation")
	float BobCyclesPerSecond = 0.6f;

private:
	FVector BaseLocation = FVector::ZeroVector;
	float Elapsed = 0.f;
};
