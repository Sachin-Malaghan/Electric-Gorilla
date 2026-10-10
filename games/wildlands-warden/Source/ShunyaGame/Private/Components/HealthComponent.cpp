// Copyright Epic Games, Inc. All Rights Reserved.

#include "Components/HealthComponent.h"
#include "Net/UnrealNetwork.h"

UHealthComponent::UHealthComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);

	MaxHealth = 100.0f;
	CurrentHealth = 100.0f;
	bIsDead = false;
}

void UHealthComponent::SetMaxHealth(float InMaxHealth, bool bResetCurrentHealth)
{
	if (!HasAuthorityOrNoOwner())
	{
		return;
	}

	MaxHealth = FMath::Max(1.0f, InMaxHealth);
	if (bResetCurrentHealth || CurrentHealth > MaxHealth)
	{
		CurrentHealth = MaxHealth;
	}
}

void UHealthComponent::BeginPlay()
{
	Super::BeginPlay();

	if (HasAuthorityOrNoOwner())
	{
		CurrentHealth = MaxHealth;
		bIsDead = (CurrentHealth <= 0.0f);
	}
}

void UHealthComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UHealthComponent, CurrentHealth);
	DOREPLIFETIME(UHealthComponent, MaxHealth);
	DOREPLIFETIME(UHealthComponent, bIsDead);
}

bool UHealthComponent::HasAuthorityOrNoOwner() const
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return true; // Unit tests or detached components have authority
	}
	return Owner->HasAuthority();
}

bool UHealthComponent::ApplyDamage(float Amount)
{
	if (!HasAuthorityOrNoOwner())
	{
		return false;
	}

	if (Amount <= 0.0f || bIsDead)
	{
		return false;
	}

	const float OldHealth = CurrentHealth;
	CurrentHealth = FMath::Clamp(CurrentHealth - Amount, 0.0f, MaxHealth);
	const float Delta = CurrentHealth - OldHealth;

	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth, Delta);
	OnHealthChangedNative.Broadcast(CurrentHealth, MaxHealth, Delta);

	if (CurrentHealth <= 0.0f && !bIsDead)
	{
		bIsDead = true;
		AActor* OwnerActor = GetOwner();
		OnDeath.Broadcast(OwnerActor);
		OnDeathNative.Broadcast(OwnerActor);
	}

	return true;
}

bool UHealthComponent::Heal(float Amount)
{
	if (!HasAuthorityOrNoOwner())
	{
		return false;
	}

	if (Amount <= 0.0f || bIsDead || CurrentHealth >= MaxHealth)
	{
		return false;
	}

	const float OldHealth = CurrentHealth;
	CurrentHealth = FMath::Clamp(CurrentHealth + Amount, 0.0f, MaxHealth);
	const float Delta = CurrentHealth - OldHealth;

	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth, Delta);
	OnHealthChangedNative.Broadcast(CurrentHealth, MaxHealth, Delta);

	return true;
}

void UHealthComponent::OnRep_CurrentHealth(float OldHealth)
{
	const float Delta = CurrentHealth - OldHealth;
	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth, Delta);
	OnHealthChangedNative.Broadcast(CurrentHealth, MaxHealth, Delta);
}

void UHealthComponent::OnRep_IsDead()
{
	if (bIsDead)
	{
		OnDeath.Broadcast(GetOwner());
		OnDeathNative.Broadcast(GetOwner());
	}
}
