// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "EnemyCharacter.generated.h"

class UHealthComponent;
class UStaticMeshComponent;

/**
 * AEnemyCharacter: Melee enemy unit that directly steers toward the player in Tick
 * without AIModule/NavMesh. Attacks on close range cadence and handles damage/death.
 */
UCLASS()
class SHUNYAGAME_API AEnemyCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AEnemyCharacter();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;
	virtual float TakeDamage(float DamageAmount, struct FDamageEvent const& DamageEvent, class AController* EventInstigator, AActor* DamageCauser) override;

	/** Get the health component */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	UHealthComponent* GetHealthComponent() const { return HealthComponent; }

	/** Movement speed in units/s (default 320.0) */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	float GetMovementSpeed() const { return MovementSpeed; }

	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	void SetMovementSpeed(float InSpeed) { MovementSpeed = InSpeed; }

	/** Attack range in units (default 120.0) */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	float GetAttackRange() const { return AttackRange; }

	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	void SetAttackRange(float InRange) { AttackRange = InRange; }

	/** Attack damage dealt to player (default 15.0) */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	float GetAttackDamage() const { return AttackDamage; }

	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	void SetAttackDamage(float InDamage) { AttackDamage = InDamage; }

	/** Cooldown between attacks in seconds (default 1.5) */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	float GetAttackCooldown() const { return AttackCooldown; }

	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	void SetAttackCooldown(float InCooldown) { AttackCooldown = InCooldown; }

	/** Current remaining attack cooldown timer */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	float GetAttackCooldownTimer() const { return AttackCooldownTimer; }

	/** Check if enemy is dead */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	bool IsDead() const { return bIsDead; }

	/** Pure/static helper to calculate steering velocity on the XY plane */
	UFUNCTION(BlueprintPure, Category="Combat|Enemy")
	static FVector CalculateSteeringVelocity(const FVector& CurrentPos, const FVector& TargetPos, float Speed);

	/** Headless update step for AI decision logic, cooldowns, steering and attacks */
	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	void UpdateEnemyLogic(float DeltaTime, const FVector& TargetLocation, AActor* TargetActor = nullptr);

	/** Explicitly execute attack against target actor */
	UFUNCTION(BlueprintCallable, Category="Combat|Enemy")
	bool ExecuteAttack(AActor* TargetActor);

	/** Target actor being pursued (usually the player character/pawn) */
	UPROPERTY(Transient, BlueprintReadWrite, Category="Combat|Enemy")
	TWeakObjectPtr<AActor> TargetActor;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Combat|Health")
	TObjectPtr<UHealthComponent> HealthComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Visual")
	TObjectPtr<UStaticMeshComponent> VisualMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Enemy")
	float MovementSpeed;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Enemy")
	float AttackRange;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Enemy")
	float AttackDamage;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Combat|Enemy")
	float AttackCooldown;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Enemy")
	float AttackCooldownTimer;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Enemy")
	bool bIsDead;

	UFUNCTION()
	void HandleDeath(AActor* DeadActor);

	virtual void OnDeath();
};
