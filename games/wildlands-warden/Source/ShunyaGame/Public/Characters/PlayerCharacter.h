// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "PlayerCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UStaticMeshComponent;
class UHealthComponent;
class UStaminaComponent;

/**
 * Third-person player character for ShunyaGame.
 * Assembled from basic shapes (/Engine/BasicShapes/Cylinder, /Engine/BasicShapes/Cube).
 * Features WASD movement, Sprint, Dodge impulse, and Light/Heavy melee attacks with stamina gating.
 */
UCLASS()
class SHUNYAGAME_API APlayerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	APlayerCharacter();

	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;
	virtual void Tick(float DeltaSeconds) override;

	// Components
	UFUNCTION(BlueprintPure, Category="Player|Components")
	USpringArmComponent* GetCameraBoom() const { return CameraBoom; }

	UFUNCTION(BlueprintPure, Category="Player|Components")
	UCameraComponent* GetFollowCamera() const { return FollowCamera; }

	UFUNCTION(BlueprintPure, Category="Player|Components")
	UStaticMeshComponent* GetBodyMesh() const { return BodyMesh; }

	UFUNCTION(BlueprintPure, Category="Player|Components")
	UStaticMeshComponent* GetWeaponMesh() const { return WeaponMesh; }

	UFUNCTION(BlueprintPure, Category="Player|Components")
	UHealthComponent* GetHealthComponent() const { return HealthComponent; }

	UFUNCTION(BlueprintPure, Category="Player|Components")
	UStaminaComponent* GetStaminaComponent() const { return StaminaComponent; }

	// Movement / Locomotion
	UFUNCTION(BlueprintCallable, Category="Player|Locomotion")
	void StartSprint();

	UFUNCTION(BlueprintCallable, Category="Player|Locomotion")
	void StopSprint();

	UFUNCTION(BlueprintPure, Category="Player|Locomotion")
	bool IsSprinting() const { return bIsSprinting; }

	/** Update sprint drain and speed - callable directly in tick or in headless unit tests */
	UFUNCTION(BlueprintCallable, Category="Player|Locomotion")
	void UpdateSprint(float DeltaTime);

	// Dodge
	UFUNCTION(BlueprintCallable, Category="Player|Combat")
	bool PerformDodge();

	UFUNCTION(BlueprintPure, Category="Player|Combat")
	bool IsDodging() const { return bIsDodging; }

	UFUNCTION(BlueprintPure, Category="Player|Combat")
	float GetDodgeCooldownRemaining() const { return DodgeCooldownTimer; }

	/** Update dodge timers - callable directly in tick or in headless unit tests */
	UFUNCTION(BlueprintCallable, Category="Player|Combat")
	void UpdateDodge(float DeltaTime);

	// Attacks
	UFUNCTION(BlueprintCallable, Category="Player|Combat")
	bool PerformLightAttack();

	UFUNCTION(BlueprintCallable, Category="Player|Combat")
	bool PerformHeavyAttack();

	UFUNCTION(BlueprintPure, Category="Player|Combat")
	float GetHeavyAttackCooldownRemaining() const { return HeavyAttackCooldownTimer; }

	/** Update attack cooldowns - callable directly in tick or in headless unit tests */
	UFUNCTION(BlueprintCallable, Category="Player|Combat")
	void UpdateCombatTimers(float DeltaTime);

	// Movement Input handlers
	void MoveForward(float Value);
	void MoveRight(float Value);
	void Turn(float Value);
	void LookUp(float Value);

	void OnDodgePressed() { PerformDodge(); }
	void OnLightAttackPressed() { PerformLightAttack(); }
	void OnHeavyAttackPressed() { PerformHeavyAttack(); }
	void OnRestartPressed();

	// Constants / Config
	static constexpr float BaseWalkSpeed = 400.0f;
	static constexpr float SprintSpeed = 700.0f;
	static constexpr float SprintStaminaCostRate = 20.0f; // per second

	static constexpr float DodgeStaminaCost = 25.0f;
	static constexpr float DodgeCooldownDuration = 0.5f;
	static constexpr float DodgeImpulseStrength = 1500.0f;
	static constexpr float DodgeDuration = 0.3f;

	static constexpr float LightAttackStaminaCost = 15.0f;
	static constexpr float LightAttackDamage = 25.0f;
	static constexpr float LightAttackRange = 150.0f;

	static constexpr float HeavyAttackStaminaCost = 35.0f;
	static constexpr float HeavyAttackDamage = 60.0f;
	static constexpr float HeavyAttackRange = 180.0f;
	static constexpr float HeavyAttackCooldownDuration = 3.0f;

protected:
	virtual void BeginPlay() override;

	/** Perform melee overlap/trace detection in front of character */
	int32 ExecuteMeleeHitDetection(float Range, float Damage);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
	TObjectPtr<UCameraComponent> FollowCamera;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Visuals")
	TObjectPtr<UStaticMeshComponent> BodyMesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Visuals")
	TObjectPtr<UStaticMeshComponent> WeaponMesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Combat")
	TObjectPtr<UHealthComponent> HealthComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Combat")
	TObjectPtr<UStaminaComponent> StaminaComponent;

	// State flags and timers
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Player|Locomotion")
	bool bIsSprinting;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Player|Combat")
	bool bIsDodging;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Player|Combat")
	float DodgeCooldownTimer;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Player|Combat")
	float DodgeDurationTimer;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Player|Combat")
	float HeavyAttackCooldownTimer;

	FVector LastMovementInputVector;
};
