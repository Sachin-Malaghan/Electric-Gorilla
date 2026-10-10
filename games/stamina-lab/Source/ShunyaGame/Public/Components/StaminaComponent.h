// Copyright Shunya Studios. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "StaminaComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnStaminaDepletedSignature);
DECLARE_MULTICAST_DELEGATE(FOnStaminaDepletedNativeSignature);

/**
 * UStaminaComponent
 * Reusable, server-authoritative stamina component managing current/max stamina,
 * consumption, delayed regeneration, and depletion events.
 */
UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class SHUNYAGAME_API UStaminaComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UStaminaComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Manually advances stamina regeneration by DeltaTime (also called by TickComponent). */
	UFUNCTION(BlueprintCallable, Category = "Stamina")
	void RegenerateStamina(float DeltaTime);

	/** Returns current stamina value */
	UFUNCTION(BlueprintPure, Category = "Stamina")
	float GetCurrentStamina() const { return CurrentStamina; }

	/** Returns maximum stamina value */
	UFUNCTION(BlueprintPure, Category = "Stamina")
	float GetMaxStamina() const { return MaxStamina; }

	/** Returns stamina regeneration rate in units per second */
	UFUNCTION(BlueprintPure, Category = "Stamina")
	float GetStaminaRegenRate() const { return StaminaRegenRate; }

	/** Returns delay in seconds after consumption before regeneration begins */
	UFUNCTION(BlueprintPure, Category = "Stamina")
	float GetStaminaRegenDelay() const { return StaminaRegenDelay; }

	/** Mutator to consume stamina. Decrements CurrentStamina, clamped at 0. Ignores Amount <= 0. */
	UFUNCTION(BlueprintCallable, Category = "Stamina")
	void ConsumeStamina(float Amount);

	/** Sets max stamina and clamps current stamina if needed. */
	UFUNCTION(BlueprintCallable, Category = "Stamina")
	void SetMaxStamina(float InMaxStamina);

	/** Sets stamina regeneration rate in units per second. */
	UFUNCTION(BlueprintCallable, Category = "Stamina")
	void SetStaminaRegenRate(float InRate);

	/** Sets stamina regeneration delay in seconds. */
	UFUNCTION(BlueprintCallable, Category = "Stamina")
	void SetStaminaRegenDelay(float InDelay);

	/** Multicast dynamic delegate broadcast when stamina reaches 0 from a positive value. */
	UPROPERTY(BlueprintAssignable, Category = "Stamina")
	FOnStaminaDepletedSignature OnStaminaDepleted;

	/** Multicast native delegate broadcast when stamina reaches 0 from a positive value. */
	FOnStaminaDepletedNativeSignature OnStaminaDepletedNative;

protected:
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, ReplicatedUsing = OnRep_CurrentStamina, Category = "Stamina")
	float CurrentStamina;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_MaxStamina, Category = "Stamina", meta = (ClampMin = "0.0"))
	float MaxStamina;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "Stamina", meta = (ClampMin = "0.0"))
	float StaminaRegenRate;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Replicated, Category = "Stamina", meta = (ClampMin = "0.0"))
	float StaminaRegenDelay;

	UFUNCTION()
	virtual void OnRep_CurrentStamina(float OldStamina);

	UFUNCTION()
	virtual void OnRep_MaxStamina();

private:
	UPROPERTY()
	float TimeSinceLastConsumption;
};
