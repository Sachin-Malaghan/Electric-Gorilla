// Reusable health pool for any actor. Server-authoritative and replicated.

#include "Components/HealthComponent.h"

#include "GameFramework/Actor.h"
#include "Net/UnrealNetwork.h"

UHealthComponent::UHealthComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
	Health = MaxHealth;
}

void UHealthComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UHealthComponent, MaxHealth);
	DOREPLIFETIME(UHealthComponent, Health);
	DOREPLIFETIME(UHealthComponent, bIsDead);
}

bool UHealthComponent::CanMutate() const
{
	const AActor* Owner = GetOwner();
	return Owner == nullptr || Owner->HasAuthority();
}

float UHealthComponent::ApplyDamage(float Amount)
{
	if (!CanMutate() || bIsDead || Amount <= 0.f)
	{
		return 0.f;
	}
	const float OldHealth = Health;
	Health = FMath::Clamp(Health - Amount, 0.f, MaxHealth);
	const float Applied = OldHealth - Health;
	if (Applied > 0.f)
	{
		OnHealthChanged.Broadcast(this, Health, -Applied);
	}
	if (Health <= 0.f && !bIsDead)
	{
		bIsDead = true;
		OnDeath.Broadcast(this);
		OnDeathNative.Broadcast(this);
	}
	return Applied;
}

float UHealthComponent::Heal(float Amount)
{
	if (!CanMutate() || bIsDead || Amount <= 0.f)
	{
		return 0.f;
	}
	const float OldHealth = Health;
	Health = FMath::Clamp(Health + Amount, 0.f, MaxHealth);
	const float Restored = Health - OldHealth;
	if (Restored > 0.f)
	{
		OnHealthChanged.Broadcast(this, Health, Restored);
	}
	return Restored;
}

void UHealthComponent::OnRep_Health(float OldHealth)
{
	OnHealthChanged.Broadcast(this, Health, Health - OldHealth);
}
