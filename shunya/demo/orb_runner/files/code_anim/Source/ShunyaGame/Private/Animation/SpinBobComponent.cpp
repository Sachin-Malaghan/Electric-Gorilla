// Procedural idle animation for pickups.

#include "Animation/SpinBobComponent.h"

#include "GameFramework/Actor.h"

USpinBobComponent::USpinBobComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void USpinBobComponent::BeginPlay()
{
	Super::BeginPlay();
	if (const AActor* Owner = GetOwner())
	{
		BaseLocation = Owner->GetActorLocation();
	}
}

void USpinBobComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}
	Elapsed += DeltaTime;
	const FVector Location = BaseLocation + FVector(0.f, 0.f, ComputeBobOffset(Elapsed, BobAmplitude, BobCyclesPerSecond));
	const FRotator Rotation(0.f, ComputeYaw(Elapsed, SpinDegreesPerSecond), 0.f);
	Owner->SetActorLocationAndRotation(Location, Rotation);
}

float USpinBobComponent::ComputeBobOffset(float Time, float Amplitude, float CyclesPerSecond)
{
	return Amplitude * FMath::Sin(2.f * UE_PI * CyclesPerSecond * Time);
}

float USpinBobComponent::ComputeYaw(float Time, float DegreesPerSecond)
{
	const float Yaw = FMath::Fmod(Time * DegreesPerSecond, 360.f);
	return Yaw < 0.f ? Yaw + 360.f : Yaw;
}
