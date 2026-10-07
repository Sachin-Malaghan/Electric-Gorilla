// The player pawn.

#include "Player/OrbRunnerPawn.h"

#include "Camera/CameraComponent.h"
#include "Components/HealthComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Game/OrbGameMode.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

AOrbRunnerPawn::AOrbRunnerPawn()
{
	PrimaryActorTick.bCanEverTick = true;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(50.f);
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	Collision->SetGenerateOverlapEvents(true);
	RootComponent = Collision;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Collision);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded())
	{
		Mesh->SetStaticMesh(SphereMesh.Object);
	}

	CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
	CameraArm->SetupAttachment(Collision);
	CameraArm->SetUsingAbsoluteRotation(true);
	// third-person chase camera: behind and above the player, looking forward (+X)
	CameraArm->SetRelativeRotation(FRotator(-28.f, 0.f, 0.f));
	CameraArm->TargetArmLength = 950.f;
	CameraArm->bDoCollisionTest = false;
	CameraArm->bEnableCameraLag = true;
	CameraArm->CameraLagSpeed = 6.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraArm);

	Health = CreateDefaultSubobject<UHealthComponent>(TEXT("Health"));
}

void AOrbRunnerPawn::BeginPlay()
{
	Super::BeginPlay();
	// The look is authored by the art department and may not exist yet.
	if (UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Shunya/Characters/M_Player.M_Player"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mesh->SetMaterial(0, Material);
	}
	Health->OnDeathNative.AddWeakLambda(this, [this](UHealthComponent*)
	{
		if (AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr)
		{
			GameMode->NotifyPlayerDied();
		}
	});
}

void AOrbRunnerPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr;
	if (GameMode && GameMode->GetRules().IsOver())
	{
		return;
	}
	const FVector2D Input = bUseExternalInput ? ExternalInput : ReadKeyboard();
	const FVector Delta = ComputeMoveDelta(Input, MoveSpeed, DeltaSeconds);
	if (!Delta.IsNearlyZero())
	{
		FHitResult Hit;
		AddActorWorldOffset(Delta, /*bSweep*/ true, &Hit);
		if (Hit.bBlockingHit)
		{
			// slide along walls and pillars instead of stopping dead
			const FVector Remaining = Delta * (1.f - Hit.Time);
			AddActorWorldOffset(FVector::VectorPlaneProject(Remaining, Hit.Normal), /*bSweep*/ true);
		}
		SetActorLocation(ClampToArena(GetActorLocation(), ArenaHalfExtent));
	}
}

void AOrbRunnerPawn::SetExternalMoveInput(const FVector2D& Input)
{
	ExternalInput = Input;
	bUseExternalInput = true;
}

void AOrbRunnerPawn::ClearExternalMoveInput()
{
	ExternalInput = FVector2D::ZeroVector;
	bUseExternalInput = false;
}

FVector2D AOrbRunnerPawn::ReadKeyboard() const
{
	const APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return FVector2D::ZeroVector;
	}
	auto Axis = [PC](const FKey& PositiveA, const FKey& PositiveB, const FKey& NegativeA, const FKey& NegativeB)
	{
		const float Positive = (PC->IsInputKeyDown(PositiveA) || PC->IsInputKeyDown(PositiveB)) ? 1.f : 0.f;
		const float Negative = (PC->IsInputKeyDown(NegativeA) || PC->IsInputKeyDown(NegativeB)) ? 1.f : 0.f;
		return Positive - Negative;
	};
	return FVector2D(Axis(EKeys::W, EKeys::Up, EKeys::S, EKeys::Down), Axis(EKeys::D, EKeys::Right, EKeys::A, EKeys::Left));
}

FVector AOrbRunnerPawn::ComputeMoveDelta(const FVector2D& Input, float Speed, float DeltaSeconds)
{
	if (Input.IsNearlyZero() || Speed <= 0.f || DeltaSeconds <= 0.f)
	{
		return FVector::ZeroVector;
	}
	const FVector2D Direction = Input.SizeSquared() > 1.f ? Input.GetSafeNormal() : Input;
	return FVector(Direction.X, Direction.Y, 0.f) * Speed * DeltaSeconds;
}

FVector AOrbRunnerPawn::ClampToArena(const FVector& Location, float HalfExtent)
{
	return FVector(FMath::Clamp(Location.X, -HalfExtent, HalfExtent), FMath::Clamp(Location.Y, -HalfExtent, HalfExtent), Location.Z);
}
