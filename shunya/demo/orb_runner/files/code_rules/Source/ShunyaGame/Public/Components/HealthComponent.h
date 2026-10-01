// Reusable health pool for any actor. Server-authoritative and replicated.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"

#include "HealthComponent.generated.h"

class UHealthComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnHealthChanged, UHealthComponent*, Component, float, NewHealth, float, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDeath, UHealthComponent*, Component);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnDeathNative, UHealthComponent*);

UCLASS(ClassGroup = (Shunya), meta = (BlueprintSpawnableComponent))
class SHUNYAGAME_API UHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UHealthComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Applies damage on the authority. Returns the damage actually applied (0 if dead, invalid, or not authoritative). */
	UFUNCTION(BlueprintCallable, Category = "Health")
	float ApplyDamage(float Amount);

	/** Restores health on the authority, up to MaxHealth. Has no effect once dead. Returns the amount restored. */
	UFUNCTION(BlueprintCallable, Category = "Health")
	float Heal(float Amount);

	UFUNCTION(BlueprintPure, Category = "Health")
	float GetHealth() const { return Health; }

	UFUNCTION(BlueprintPure, Category = "Health")
	float GetMaxHealth() const { return MaxHealth; }

	UFUNCTION(BlueprintPure, Category = "Health")
	bool IsDead() const { return bIsDead; }

	UPROPERTY(BlueprintAssignable, Category = "Health")
	FOnHealthChanged OnHealthChanged;

	/** Fires exactly once, when health first reaches zero. */
	UPROPERTY(BlueprintAssignable, Category = "Health")
	FOnDeath OnDeath;

	/** Native counterpart of OnDeath for C++ listeners. */
	FOnDeathNative OnDeathNative;

protected:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Replicated, Category = "Health", meta = (ClampMin = "1.0"))
	float MaxHealth = 100.f;

	UPROPERTY(BlueprintReadOnly, ReplicatedUsing = OnRep_Health, Category = "Health")
	float Health = 100.f;

	UPROPERTY(BlueprintReadOnly, Replicated, Category = "Health")
	bool bIsDead = false;

	UFUNCTION()
	void OnRep_Health(float OldHealth);

private:
	/** True on the server, and for ownerless components (unit tests). */
	bool CanMutate() const;
};
