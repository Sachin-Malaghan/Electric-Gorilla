// The threat: a drone that homes in on the player and drains health on contact.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "ChaserDrone.generated.h"

class USphereComponent;
class UStaticMeshComponent;

UCLASS()
class SHUNYAGAME_API AChaserDrone : public AActor
{
	GENERATED_BODY()

public:
	AChaserDrone();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** One frame of pursuit on the ground plane: moves toward To at Speed and never overshoots it. */
	static FVector ComputeSteer(const FVector& From, const FVector& To, float Speed, float DeltaSeconds);

	/** True when enough time has passed since the last hit to hit again. */
	static bool CanDamage(float TimeSinceLastHit, float Cooldown);

	/** Units per second (Docs/Design/ThreatSpec.md). Slower than the player so the player can always escape. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Drone")
	float Speed = 260.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Drone")
	float ContactDamage = 25.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Drone")
	float DamageCooldown = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Drone")
	float ContactRadius = 130.f;

private:
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USphereComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Mesh;

	float TimeSinceLastHit = 1000.f;
};
