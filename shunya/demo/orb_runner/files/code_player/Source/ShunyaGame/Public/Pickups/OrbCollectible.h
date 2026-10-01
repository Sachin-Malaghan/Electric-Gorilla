// A glowing orb. Touching it with the player pawn scores points and removes it.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OrbCollectible.generated.h"

class UPointLightComponent;
class USphereComponent;
class USpinBobComponent;
class UStaticMeshComponent;

UCLASS()
class SHUNYAGAME_API AOrbCollectible : public AActor
{
	GENERATED_BODY()

public:
	AOrbCollectible();

	virtual void BeginPlay() override;

	/** Points awarded when collected (Docs/Design/Tuning.md). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Orb")
	int32 Value = 10;

	USpinBobComponent* GetSpinBob() const { return SpinBob; }

private:
	UFUNCTION()
	void HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UPointLightComponent> Glow;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USpinBobComponent> SpinBob;

	bool bCollected = false;
};
