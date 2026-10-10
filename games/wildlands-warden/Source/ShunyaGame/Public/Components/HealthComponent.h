// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HealthComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnHealthChangedSignature, float, CurrentHealth, float, MaxHealth, float, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDeathSignature, AActor*, DeadActor);

DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnHealthChangedNativeSignature, float, float, float);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnDeathNativeSignature, AActor*);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class SHUNYAGAME_API UHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UHealthComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Get current health */
	UFUNCTION(BlueprintPure, Category="Combat|Health")
	float GetHealth() const { return CurrentHealth; }

	/** Get max health */
	UFUNCTION(BlueprintPure, Category="Combat|Health")
	float GetMaxHealth() const { return MaxHealth; }

	/** Set max health (also resets current health if specified) */
	UFUNCTION(BlueprintCallable, Category="Combat|Health")
	void SetMaxHealth(float InMaxHealth, bool bResetCurrentHealth = false);


	/** Check if dead */
	UFUNCTION(BlueprintPure, Category="Combat|Health")
	bool IsDead() const { return bIsDead; }

	/** Get current health percentage [0.0, 1.0] */
	UFUNCTION(BlueprintPure, Category="Combat|Health")
	float GetHealthPercent() const { return MaxHealth > 0.0f ? (CurrentHealth / MaxHealth) : 0.0f; }

	/** Apply damage. Amount must be positive. Clamps health >= 0. */
	UFUNCTION(BlueprintCallable, Category="Combat|Health")
	bool ApplyDamage(float Amount);

	/** Heal health. Amount must be positive. Clamps health <= MaxHealth. */
	UFUNCTION(BlueprintCallable, Category="Combat|Health")
	bool Heal(float Amount);

	/** Dynamic delegate fired when health changes */
	UPROPERTY(BlueprintAssignable, Category="Combat|Health")
	FOnHealthChangedSignature OnHealthChanged;

	/** Dynamic delegate fired once when health reaches 0 */
	UPROPERTY(BlueprintAssignable, Category="Combat|Health")
	FOnDeathSignature OnDeath;

	/** Native delegate fired when health changes */
	FOnHealthChangedNativeSignature OnHealthChangedNative;

	/** Native delegate fired once when health reaches 0 */
	FOnDeathNativeSignature OnDeathNative;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(ReplicatedUsing=OnRep_CurrentHealth, VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Health")
	float CurrentHealth;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category="Combat|Health", meta=(ClampMin="1.0"))
	float MaxHealth;

	UPROPERTY(ReplicatedUsing=OnRep_IsDead, VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Health")
	bool bIsDead;

	UFUNCTION()
	void OnRep_CurrentHealth(float OldHealth);

	UFUNCTION()
	void OnRep_IsDead();

private:
	bool HasAuthorityOrNoOwner() const;
};
