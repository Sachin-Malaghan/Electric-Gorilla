// The player: a rolling sphere seen from above. WASD / arrow keys move it; bots can drive it too.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"

#include "OrbRunnerPawn.generated.h"

class UCameraComponent;
class UHealthComponent;
class USphereComponent;
class USpringArmComponent;
class UStaticMeshComponent;

UCLASS()
class SHUNYAGAME_API AOrbRunnerPawn : public APawn
{
	GENERATED_BODY()

public:
	AOrbRunnerPawn();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Drive the pawn from code (QA bot, tests). X is forward (+X world), Y is right (+Y world). Replaces the keyboard until cleared. */
	void SetExternalMoveInput(const FVector2D& Input);
	void ClearExternalMoveInput();

	/** World-space movement for one frame. Diagonal input is normalised so it is not faster. */
	static FVector ComputeMoveDelta(const FVector2D& Input, float Speed, float DeltaSeconds);

	/** Keeps a location inside the square arena. Z is untouched. */
	static FVector ClampToArena(const FVector& Location, float HalfExtent);

	UHealthComponent* GetHealth() const { return Health; }

	UPROPERTY(EditDefaultsOnly, Category = "Movement")
	float MoveSpeed = 700.f;

	UPROPERTY(EditDefaultsOnly, Category = "Movement")
	float ArenaHalfExtent = 1850.f;

private:
	FVector2D ReadKeyboard() const;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USphereComponent> Collision;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UHealthComponent> Health;

	FVector2D ExternalInput = FVector2D::ZeroVector;
	bool bUseExternalInput = false;
};
