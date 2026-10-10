// Copyright Epic Games, Inc. All Rights Reserved.

#include "Characters/PlayerCharacter.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InputComponent.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"
#include "ShunyaCombatGameMode.h"
#include "UObject/ConstructorHelpers.h"
#include "Engine/World.h"
#include "Engine/OverlapResult.h"
#include "CollisionQueryParams.h"

APlayerCharacter::APlayerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	// Set size for collision capsule
	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.0f);

	// Don't rotate when the controller rotates. Let that just affect the camera.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	// Configure character movement
	if (GetCharacterMovement())
	{
		GetCharacterMovement()->bOrientRotationToMovement = true;
		GetCharacterMovement()->RotationRate = FRotator(0.0f, 540.0f, 0.0f);
		GetCharacterMovement()->MaxWalkSpeed = BaseWalkSpeed;
	}

	// Create BodyMesh from Cylinder
	BodyMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BodyMesh"));
	BodyMesh->SetupAttachment(RootComponent);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMeshAsset(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (CylinderMeshAsset.Succeeded())
	{
		BodyMesh->SetStaticMesh(CylinderMeshAsset.Object);
		// Cylinder basic shape has height ~100 and diameter ~100.
		// Scale to fit character capsule (Capsule half height 96, radius 42)
		BodyMesh->SetRelativeScale3D(FVector(0.84f, 0.84f, 1.92f));
		BodyMesh->SetRelativeLocation(FVector(0.0f, 0.0f, 0.0f));
	}
	BodyMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// Create WeaponMesh from Cube
	WeaponMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(BodyMesh);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMeshAsset(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMeshAsset.Succeeded())
	{
		WeaponMesh->SetStaticMesh(CubeMeshAsset.Object);
		// Scale cube as sword/baton: 15cm wide, 15cm thick, 80cm long
		WeaponMesh->SetRelativeScale3D(FVector(0.15f, 0.15f, 0.8f));
		WeaponMesh->SetRelativeLocation(FVector(40.0f, 30.0f, 10.0f));
		WeaponMesh->SetRelativeRotation(FRotator(45.0f, 0.0f, 0.0f));
	}
	WeaponMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// Create CameraBoom (pulls in towards the player if there is a collision)
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.0f;
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->SetRelativeLocation(FVector(0.0f, 0.0f, 60.0f));

	// Create FollowCamera
	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;

	// Reusable gameplay components
	HealthComponent = CreateDefaultSubobject<UHealthComponent>(TEXT("HealthComponent"));
	StaminaComponent = CreateDefaultSubobject<UStaminaComponent>(TEXT("StaminaComponent"));

	// Initialize states
	bIsSprinting = false;
	bIsDodging = false;
	DodgeCooldownTimer = 0.0f;
	DodgeDurationTimer = 0.0f;
	HeavyAttackCooldownTimer = 0.0f;
	LastMovementInputVector = FVector::ForwardVector;
}

void APlayerCharacter::BeginPlay()
{
	Super::BeginPlay();

	if (GetCharacterMovement())
	{
		GetCharacterMovement()->MaxWalkSpeed = BaseWalkSpeed;
	}
}

void APlayerCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	UpdateSprint(DeltaSeconds);
	UpdateDodge(DeltaSeconds);
	UpdateCombatTimers(DeltaSeconds);
}

void APlayerCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	check(PlayerInputComponent);

	// WASD Movement
	PlayerInputComponent->BindAxisKey(EKeys::W, this, &APlayerCharacter::MoveForward);
	PlayerInputComponent->BindAxisKey(EKeys::S, this, &APlayerCharacter::MoveForward);
	PlayerInputComponent->BindAxisKey(EKeys::A, this, &APlayerCharacter::MoveRight);
	PlayerInputComponent->BindAxisKey(EKeys::D, this, &APlayerCharacter::MoveRight);

	// Mouse Look
	PlayerInputComponent->BindAxisKey(EKeys::MouseX, this, &APlayerCharacter::Turn);
	PlayerInputComponent->BindAxisKey(EKeys::MouseY, this, &APlayerCharacter::LookUp);

	// Sprint toggle/hold: Left Shift
	PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Pressed, this, &APlayerCharacter::StartSprint);
	PlayerInputComponent->BindKey(EKeys::LeftShift, IE_Released, this, &APlayerCharacter::StopSprint);

	// Dodge: SpaceBar
	PlayerInputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &APlayerCharacter::OnDodgePressed);

	// Attacks: Left Mouse Button for Light Attack, Right Mouse Button for Heavy Attack
	PlayerInputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &APlayerCharacter::OnLightAttackPressed);
	PlayerInputComponent->BindKey(EKeys::RightMouseButton, IE_Pressed, this, &APlayerCharacter::OnHeavyAttackPressed);

	// Restart: R key (in GameOver or Victory states)
	PlayerInputComponent->BindKey(EKeys::R, IE_Pressed, this, &APlayerCharacter::OnRestartPressed);
}

void APlayerCharacter::MoveForward(float Value)
{
	if (Controller && Value != 0.0f && !bIsDodging)
	{
		const FRotator Rotation = Controller->GetControlRotation();
		const FRotator YawRotation(0.0f, Rotation.Yaw, 0.0f);
		const FVector Direction = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X);
		AddMovementInput(Direction, Value);

		if (FMath::Abs(Value) > 0.1f)
		{
			LastMovementInputVector = (Direction * Value).GetSafeNormal();
		}
	}
}

void APlayerCharacter::MoveRight(float Value)
{
	if (Controller && Value != 0.0f && !bIsDodging)
	{
		const FRotator Rotation = Controller->GetControlRotation();
		const FRotator YawRotation(0.0f, Rotation.Yaw, 0.0f);
		const FVector Direction = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y);
		AddMovementInput(Direction, Value);

		if (FMath::Abs(Value) > 0.1f)
		{
			LastMovementInputVector = (Direction * Value).GetSafeNormal();
		}
	}
}

void APlayerCharacter::Turn(float Value)
{
	AddControllerYawInput(Value);
}

void APlayerCharacter::LookUp(float Value)
{
	AddControllerPitchInput(Value);
}

void APlayerCharacter::StartSprint()
{
	if (!StaminaComponent || StaminaComponent->GetStamina() <= 0.0f)
	{
		bIsSprinting = false;
		return;
	}

	bIsSprinting = true;
	if (GetCharacterMovement())
	{
		GetCharacterMovement()->MaxWalkSpeed = SprintSpeed;
	}
}

void APlayerCharacter::StopSprint()
{
	bIsSprinting = false;
	if (GetCharacterMovement())
	{
		GetCharacterMovement()->MaxWalkSpeed = BaseWalkSpeed;
	}
	if (StaminaComponent)
	{
		StaminaComponent->ResetRegenDelay();
	}
}

void APlayerCharacter::UpdateSprint(float DeltaTime)
{
	if (!bIsSprinting)
	{
		return;
	}

	if (!StaminaComponent)
	{
		StopSprint();
		return;
	}

	const float DrainAmount = SprintStaminaCostRate * DeltaTime;
	if (!StaminaComponent->ConsumeStamina(DrainAmount))
	{
		// Insufficient stamina: drop back to base walk speed
		StopSprint();
		return;
	}

	// Double check if stamina ran out
	if (StaminaComponent->GetStamina() <= 0.0f)
	{
		StopSprint();
	}
	else if (GetCharacterMovement())
	{
		GetCharacterMovement()->MaxWalkSpeed = SprintSpeed;
	}
}

bool APlayerCharacter::PerformDodge()
{
	if (bIsDodging || DodgeCooldownTimer > 0.0f)
	{
		return false;
	}

	if (!StaminaComponent || !StaminaComponent->ConsumeStamina(DodgeStaminaCost))
	{
		return false;
	}

	bIsDodging = true;
	DodgeDurationTimer = DodgeDuration;
	DodgeCooldownTimer = DodgeCooldownDuration;

	// Launch or apply impulse in last movement direction or forward
	FVector DodgeDirection = LastMovementInputVector;
	if (DodgeDirection.IsNearlyZero())
	{
		DodgeDirection = GetActorForwardVector();
	}
	DodgeDirection.Z = 0.0f;
	DodgeDirection.Normalize();

	LaunchCharacter(DodgeDirection * DodgeImpulseStrength, true, false);
	return true;
}

void APlayerCharacter::UpdateDodge(float DeltaTime)
{
	if (DodgeCooldownTimer > 0.0f)
	{
		DodgeCooldownTimer = FMath::Max(0.0f, DodgeCooldownTimer - DeltaTime);
	}

	if (bIsDodging)
	{
		DodgeDurationTimer -= DeltaTime;
		if (DodgeDurationTimer <= 0.0f)
		{
			bIsDodging = false;
			DodgeDurationTimer = 0.0f;
		}
	}
}

bool APlayerCharacter::PerformLightAttack()
{
	if (bIsDodging)
	{
		return false;
	}

	if (!StaminaComponent || !StaminaComponent->ConsumeStamina(LightAttackStaminaCost))
	{
		return false;
	}

	ExecuteMeleeHitDetection(LightAttackRange, LightAttackDamage);
	return true;
}

bool APlayerCharacter::PerformHeavyAttack()
{
	if (bIsDodging || HeavyAttackCooldownTimer > 0.0f)
	{
		return false;
	}

	if (!StaminaComponent || !StaminaComponent->ConsumeStamina(HeavyAttackStaminaCost))
	{
		return false;
	}

	HeavyAttackCooldownTimer = HeavyAttackCooldownDuration;
	ExecuteMeleeHitDetection(HeavyAttackRange, HeavyAttackDamage);
	return true;
}

void APlayerCharacter::UpdateCombatTimers(float DeltaTime)
{
	if (HeavyAttackCooldownTimer > 0.0f)
	{
		HeavyAttackCooldownTimer = FMath::Max(0.0f, HeavyAttackCooldownTimer - DeltaTime);
	}
}

void APlayerCharacter::OnRestartPressed()
{
	if (UWorld* World = GetWorld())
	{
		if (AShunyaCombatGameMode* GM = Cast<AShunyaCombatGameMode>(World->GetAuthGameMode()))
		{
			const ECombatMatchState MatchState = GM->GetCombatMatchState();
			if (MatchState == ECombatMatchState::GameOver || MatchState == ECombatMatchState::Victory)
			{
				GM->RestartMatch();
			}
		}
	}
}

int32 APlayerCharacter::ExecuteMeleeHitDetection(float Range, float Damage)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return 0;
	}

	const FVector Start = GetActorLocation();
	const FVector Forward = GetActorForwardVector();
	const FVector SphereCenter = Start + (Forward * (Range * 0.5f));

	TArray<FOverlapResult> Overlaps;
	FCollisionShape SphereShape = FCollisionShape::MakeSphere(Range * 0.5f);
	FCollisionQueryParams QueryParams;
	QueryParams.AddIgnoredActor(this);

	const bool bHit = World->OverlapMultiByChannel(
		Overlaps,
		SphereCenter,
		FQuat::Identity,
		ECC_Pawn,
		SphereShape,
		QueryParams
	);

	int32 HitCount = 0;
	if (bHit)
	{
		TSet<AActor*> DamagedActors;
		for (const FOverlapResult& Overlap : Overlaps)
		{
			AActor* TargetActor = Overlap.GetActor();
			if (TargetActor && TargetActor != this && !DamagedActors.Contains(TargetActor))
			{
				DamagedActors.Add(TargetActor);
				// Check for HealthComponent or direct damage
				UHealthComponent* TargetHealth = TargetActor->FindComponentByClass<UHealthComponent>();
				if (TargetHealth)
				{
					TargetHealth->ApplyDamage(Damage);
				}
				HitCount++;
			}
		}
	}

	return HitCount;
}
