// Copyright Epic Games, Inc. All Rights Reserved.

#include "Characters/EnemyCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DamageEvents.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

AEnemyCharacter::AEnemyCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	MovementSpeed = 320.0f;
	AttackRange = 120.0f;
	AttackDamage = 15.0f;
	AttackCooldown = 1.5f;
	AttackCooldownTimer = 0.0f;
	bIsDead = false;

	// Health Component setup (Default 50 Health per AC 1 & GDD 4.1)
	HealthComponent = CreateDefaultSubobject<UHealthComponent>(TEXT("HealthComponent"));
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(50.0f, true);
		HealthComponent->OnDeathNative.AddUObject(this, &AEnemyCharacter::HandleDeath);
	}

	// Character Movement setup
	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->MaxWalkSpeed = MovementSpeed;
	}

	// Visual mesh setup (Cylinder basic shape with red tint)
	VisualMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("VisualMesh"));
	if (VisualMesh)
	{
		VisualMesh->SetupAttachment(GetCapsuleComponent());
		VisualMesh->SetRelativeLocation(FVector(0.0f, 0.0f, -88.0f));
		VisualMesh->SetRelativeScale3D(FVector(0.7f, 0.7f, 1.76f));
		VisualMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

		if (!IsRunningCommandlet())
		{
			static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMeshAsset(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
			if (CylinderMeshAsset.Succeeded())
			{
				VisualMesh->SetStaticMesh(CylinderMeshAsset.Object);
			}

			static ConstructorHelpers::FObjectFinder<UMaterialInterface> BaseMaterialAsset(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
			if (BaseMaterialAsset.Succeeded())
			{
				VisualMesh->SetMaterial(0, BaseMaterialAsset.Object);
			}
		}
	}
}

void AEnemyCharacter::BeginPlay()
{
	Super::BeginPlay();

	// Create dynamic material instance for red tint
	if (VisualMesh)
	{
		UMaterialInstanceDynamic* DynMat = VisualMesh->CreateAndSetMaterialInstanceDynamic(0);
		if (DynMat)
		{
			DynMat->SetVectorParameterValue(TEXT("Color"), FLinearColor::Red);
		}
	}
}

float AEnemyCharacter::TakeDamage(float DamageAmount, struct FDamageEvent const& DamageEvent, class AController* EventInstigator, AActor* DamageCauser)
{
	float ActualDamage = DamageAmount;
	// Only call Super::TakeDamage if we are in a valid world (AActor::TakeDamage delegates to GameMode and needs UWorld)
	if (GetWorld())
	{
		ActualDamage = Super::TakeDamage(DamageAmount, DamageEvent, EventInstigator, DamageCauser);
	}

	if (ActualDamage > 0.0f && HealthComponent && !bIsDead)
	{
		HealthComponent->ApplyDamage(ActualDamage);
	}
	return ActualDamage;
}

void AEnemyCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (bIsDead)
	{
		return;
	}

	// Resolve target player if null or invalid
	if (!TargetActor.IsValid())
	{
		APawn* PlayerPawn = UGameplayStatics::GetPlayerPawn(this, 0);
		if (PlayerPawn)
		{
			TargetActor = PlayerPawn;
		}
	}

	if (TargetActor.IsValid())
	{
		UpdateEnemyLogic(DeltaTime, TargetActor->GetActorLocation(), TargetActor.Get());
	}
	else
	{
		// Cooldown ticking even without target
		if (AttackCooldownTimer > 0.0f)
		{
			AttackCooldownTimer = FMath::Max(0.0f, AttackCooldownTimer - DeltaTime);
		}
	}
}

FVector AEnemyCharacter::CalculateSteeringVelocity(const FVector& CurrentPos, const FVector& TargetPos, float Speed)
{
	FVector Direction = (TargetPos - CurrentPos);
	Direction.Z = 0.0f; // XY plane only

	if (Direction.IsNearlyZero())
	{
		return FVector::ZeroVector;
	}

	return Direction.GetSafeNormal() * Speed;
}

void AEnemyCharacter::UpdateEnemyLogic(float DeltaTime, const FVector& TargetLocation, AActor* InTargetActor)
{
	if (bIsDead || DeltaTime <= 0.0f)
	{
		return;
	}

	// Tick attack cooldown timer
	if (AttackCooldownTimer > 0.0f)
	{
		AttackCooldownTimer = FMath::Max(0.0f, AttackCooldownTimer - DeltaTime);
	}

	// Calculate XY planar distance to target
	FVector CurrentLocation = GetActorLocation();
	FVector Offset = TargetLocation - CurrentLocation;
	Offset.Z = 0.0f;
	float DistanceXY = Offset.Size();

	if (DistanceXY <= AttackRange)
	{
		// Within attack range: halt movement and strike on cooldown
		if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
		{
			MoveComp->Velocity = FVector::ZeroVector;
		}

		if (AttackCooldownTimer <= 0.0f)
		{
			ExecuteAttack(InTargetActor);
		}
	}
	else
	{
		// Outside attack range: steer directly toward target on XY plane at MovementSpeed
		FVector SteeringVelocity = CalculateSteeringVelocity(CurrentLocation, TargetLocation, MovementSpeed);
		
		// If world movement component is present, add movement input
		if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
		{
			MoveComp->MaxWalkSpeed = MovementSpeed;
			AddMovementInput(SteeringVelocity.GetSafeNormal(), 1.0f);
		}
		else
		{
			// Headless / detached position step support
			SetActorLocation(CurrentLocation + SteeringVelocity * DeltaTime);
		}
	}
}

bool AEnemyCharacter::ExecuteAttack(AActor* InTargetActor)
{
	if (bIsDead || AttackCooldownTimer > 0.0f)
	{
		return false;
	}

	AttackCooldownTimer = AttackCooldown;

	if (InTargetActor)
	{
		// Try dealing damage via UHealthComponent if target has one
		UHealthComponent* TargetHealthComp = InTargetActor->FindComponentByClass<UHealthComponent>();
		if (TargetHealthComp)
		{
			TargetHealthComp->ApplyDamage(AttackDamage);
		}
		else
		{
			// Also support standard engine TakeDamage
			InTargetActor->TakeDamage(AttackDamage, FDamageEvent(), GetController(), this);
		}
	}

	return true;
}

void AEnemyCharacter::HandleDeath(AActor* DeadActor)
{
	if (bIsDead)
	{
		return;
	}

	bIsDead = true;
	OnDeath();
}

void AEnemyCharacter::OnDeath()
{
	// Halt movement and disable collisions
	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->DisableMovement();
		MoveComp->StopMovementImmediately();
	}

	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	// Destroy self or ragdoll if in world
	if (GetWorld())
	{
		Destroy();
	}
}
