// Copyright Shunya Studios. All Rights Reserved.

#include "Components/StaminaComponent.h"
#include "Net/UnrealNetwork.h"

UStaminaComponent::UStaminaComponent()
	: CurrentStamina(100.0f)
	, MaxStamina(100.0f)
	, StaminaRegenRate(20.0f)
	, StaminaRegenDelay(1.0f)
	, TimeSinceLastConsumption(1.0f) // Initialized so it can regen immediately if started below max
{
	PrimaryComponentTick.bCanEverTick = true;
	SetIsReplicatedByDefault(true);
}

void UStaminaComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UStaminaComponent, CurrentStamina);
	DOREPLIFETIME(UStaminaComponent, MaxStamina);
	DOREPLIFETIME(UStaminaComponent, StaminaRegenRate);
	DOREPLIFETIME(UStaminaComponent, StaminaRegenDelay);
}

void UStaminaComponent::ConsumeStamina(float Amount)
{
	// Check authority if owner exists
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	if (Amount <= 0.0f)
	{
		return;
	}

	const float OldStamina = CurrentStamina;
	CurrentStamina = FMath::Clamp(CurrentStamina - Amount, 0.0f, MaxStamina);
	TimeSinceLastConsumption = 0.0f;

	if (OldStamina > 0.0f && CurrentStamina == 0.0f)
	{
		OnStaminaDepleted.Broadcast();
		OnStaminaDepletedNative.Broadcast();
	}
}

void UStaminaComponent::SetMaxStamina(float InMaxStamina)
{
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	MaxStamina = FMath::Max(0.0f, InMaxStamina);
	if (CurrentStamina > MaxStamina)
	{
		CurrentStamina = MaxStamina;
	}
}

void UStaminaComponent::SetStaminaRegenRate(float InRate)
{
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	StaminaRegenRate = FMath::Max(0.0f, InRate);
}

void UStaminaComponent::SetStaminaRegenDelay(float InDelay)
{
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	StaminaRegenDelay = FMath::Max(0.0f, InDelay);
}

void UStaminaComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	RegenerateStamina(DeltaTime);
}

void UStaminaComponent::RegenerateStamina(float DeltaTime)
{
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	if (DeltaTime <= 0.0f)
	{
		return;
	}

	if (TimeSinceLastConsumption < StaminaRegenDelay)
	{
		TimeSinceLastConsumption += DeltaTime;
	}

	if (TimeSinceLastConsumption >= StaminaRegenDelay && CurrentStamina < MaxStamina && StaminaRegenRate > 0.0f)
	{
		CurrentStamina = FMath::Clamp(CurrentStamina + (StaminaRegenRate * DeltaTime), 0.0f, MaxStamina);
	}
}

void UStaminaComponent::OnRep_CurrentStamina(float OldStamina)
{
	if (OldStamina > 0.0f && CurrentStamina == 0.0f)
	{
		OnStaminaDepleted.Broadcast();
		OnStaminaDepletedNative.Broadcast();
	}
}

void UStaminaComponent::OnRep_MaxStamina()
{
}
