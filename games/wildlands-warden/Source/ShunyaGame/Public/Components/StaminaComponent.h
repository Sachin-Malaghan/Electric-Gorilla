// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "StaminaComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnStaminaChangedSignature, float, CurrentStamina, float, MaxStamina, float, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnStaminaDepletedSignature);

DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnStaminaChangedNativeSignature, float, float, float);
DECLARE_MULTICAST_DELEGATE(FOnStaminaDepletedNativeSignature);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class SHUNYAGAME_API UStaminaComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UStaminaComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Get current stamina */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetStamina() const { return CurrentStamina; }

	/** Get max stamina */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetMaxStamina() const { return MaxStamina; }

	/** Get current stamina percentage [0.0, 1.0] */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetStaminaPercent() const { return MaxStamina > 0.0f ? (CurrentStamina / MaxStamina) : 0.0f; }

	/** Get stamina regeneration rate per second */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetStaminaRegenRate() const { return StaminaRegenRate; }

	/** Get stamina regeneration delay in seconds */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetRegenDelay() const { return RegenDelay; }

	/** Get current remaining regen delay time */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	float GetCurrentRegenDelayTimer() const { return RegenDelayTimer; }

	/** Check if there is enough stamina for an action */
	UFUNCTION(BlueprintPure, Category="Combat|Stamina")
	bool HasEnoughStamina(float Amount) const { return Amount > 0.0f && CurrentStamina >= Amount; }

	/**
	 * Attempt to consume stamina.
	 * Returns true if sufficient stamina was available and consumed.
	 * Returns false and prevents action if stamina is insufficient or Amount <= 0.
	 */
	UFUNCTION(BlueprintCallable, Category="Combat|Stamina")
	bool ConsumeStamina(float Amount);

	/** Restore stamina manually. Clamps to MaxStamina. */
	UFUNCTION(BlueprintCallable, Category="Combat|Stamina")
	bool RestoreStamina(float Amount);

	/** Reset regen delay without consuming stamina (e.g. on sprint release or combat action) */
	UFUNCTION(BlueprintCallable, Category="Combat|Stamina")
	void ResetRegenDelay();

	/** Update regeneration manually - useful for headless tests or tick */
	UFUNCTION(BlueprintCallable, Category="Combat|Stamina")
	void UpdateRegeneration(float DeltaTime);

	/** Dynamic delegate fired when stamina changes */
	UPROPERTY(BlueprintAssignable, Category="Combat|Stamina")
	FOnStaminaChangedSignature OnStaminaChanged;

	/** Dynamic delegate fired when stamina drops to 0 */
	UPROPERTY(BlueprintAssignable, Category="Combat|Stamina")
	FOnStaminaDepletedSignature OnStaminaDepleted;

	/** Native delegate fired when stamina changes */
	FOnStaminaChangedNativeSignature OnStaminaChangedNative;

	/** Native delegate fired when stamina drops to 0 */
	FOnStaminaDepletedNativeSignature OnStaminaDepletedNative;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(ReplicatedUsing=OnRep_CurrentStamina, VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Stamina")
	float CurrentStamina;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Replicated, Category="Combat|Stamina", meta=(ClampMin="1.0"))
	float MaxStamina;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Combat|Stamina", meta=(ClampMin="0.0"))
	float StaminaRegenRate;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Combat|Stamina", meta=(ClampMin="0.0"))
	float RegenDelay;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Combat|Stamina")
	float RegenDelayTimer;

	UFUNCTION()
	void OnRep_CurrentStamina(float OldStamina);

private:
	bool HasAuthorityOrNoOwner() const;
};
