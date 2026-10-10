// Copyright Epic Games, Inc. All Rights Reserved.

#include "Components/StaminaComponent.h"
#include "Net/UnrealNetwork.h"

UStaminaComponent::UStaminaComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	SetIsReplicatedByDefault(true);

	MaxStamina = 100.0f;
	CurrentStamina = 100.0f;
	StaminaRegenRate = 15.0f;
	RegenDelay = 1.0f;
	RegenDelayTimer = 0.0f;
}

void UStaminaComponent::BeginPlay()
{
	Super::BeginPlay();

	if (HasAuthorityOrNoOwner())
	{
		CurrentStamina = MaxStamina;
		RegenDelayTimer = 0.0f;
	}
}

void UStaminaComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	UpdateRegeneration(DeltaTime);
}

void UStaminaComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UStaminaComponent, CurrentStamina);
	DOREPLIFETIME(UStaminaComponent, MaxStamina);
}

bool UStaminaComponent::HasAuthorityOrNoOwner() const
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return true; // Unit tests or detached components have authority
	}
	return Owner->HasAuthority();
}

bool UStaminaComponent::ConsumeStamina(float Amount)
{
	if (!HasAuthorityOrNoOwner())
	{
		return false;
	}

	if (Amount <= 0.0f)
	{
		return false;
	}

	if (CurrentStamina < Amount)
	{
		return false; // Insufficient stamina: prevent action
	}

	const float OldStamina = CurrentStamina;
	CurrentStamina = FMath::Clamp(CurrentStamina - Amount, 0.0f, MaxStamina);
	RegenDelayTimer = RegenDelay; // Reset delay timer on any stamina expenditure

	const float Delta = CurrentStamina - OldStamina;
	OnStaminaChanged.Broadcast(CurrentStamina, MaxStamina, Delta);
	OnStaminaChangedNative.Broadcast(CurrentStamina, MaxStamina, Delta);

	if (CurrentStamina <= 0.0f)
	{
		OnStaminaDepleted.Broadcast();
		OnStaminaDepletedNative.Broadcast();
	}

	return true;
}

bool UStaminaComponent::RestoreStamina(float Amount)
{
	if (!HasAuthorityOrNoOwner())
	{
		return false;
	}

	if (Amount <= 0.0f || CurrentStamina >= MaxStamina)
	{
		return false;
	}

	const float OldStamina = CurrentStamina;
	CurrentStamina = FMath::Clamp(CurrentStamina + Amount, 0.0f, MaxStamina);
	const float Delta = CurrentStamina - OldStamina;

	OnStaminaChanged.Broadcast(CurrentStamina, MaxStamina, Delta);
	OnStaminaChangedNative.Broadcast(CurrentStamina, MaxStamina, Delta);

	return true;
}

void UStaminaComponent::ResetRegenDelay()
{
	RegenDelayTimer = RegenDelay;
}

void UStaminaComponent::UpdateRegeneration(float DeltaTime)
{
	if (!HasAuthorityOrNoOwner())
	{
		return;
	}

	if (DeltaTime <= 0.0f)
	{
		return;
	}

	if (RegenDelayTimer > 0.0f)
	{
		RegenDelayTimer = FMath::Max(0.0f, RegenDelayTimer - DeltaTime);
		return;
	}

	if (CurrentStamina < MaxStamina && StaminaRegenRate > 0.0f)
	{
		const float OldStamina = CurrentStamina;
		CurrentStamina = FMath::Clamp(CurrentStamina + StaminaRegenRate * DeltaTime, 0.0f, MaxStamina);
		const float Delta = CurrentStamina - OldStamina;

		if (Delta > 0.0f)
		{
			OnStaminaChanged.Broadcast(CurrentStamina, MaxStamina, Delta);
			OnStaminaChangedNative.Broadcast(CurrentStamina, MaxStamina, Delta);
		}
	}
}

void UStaminaComponent::OnRep_CurrentStamina(float OldStamina)
{
	const float Delta = CurrentStamina - OldStamina;
	OnStaminaChanged.Broadcast(CurrentStamina, MaxStamina, Delta);
	OnStaminaChangedNative.Broadcast(CurrentStamina, MaxStamina, Delta);

	if (CurrentStamina <= 0.0f)
	{
		OnStaminaDepleted.Broadcast();
		OnStaminaDepletedNative.Broadcast();
	}
}
