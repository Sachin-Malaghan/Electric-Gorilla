// The chaser drone.

#include "AI/ChaserDrone.h"

#include "Components/HealthComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Game/OrbGameMode.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Player/OrbRunnerPawn.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

AChaserDrone::AChaserDrone()
{
	PrimaryActorTick.bCanEverTick = true;

	Body = CreateDefaultSubobject<USphereComponent>(TEXT("Body"));
	Body->InitSphereRadius(60.f);
	Body->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	RootComponent = Body;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Body);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetRelativeScale3D(FVector(1.1f, 1.1f, 0.45f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> ConeMesh(TEXT("/Engine/BasicShapes/Cone.Cone"));
	if (ConeMesh.Succeeded())
	{
		Mesh->SetStaticMesh(ConeMesh.Object);
	}
}

void AChaserDrone::BeginPlay()
{
	Super::BeginPlay();
	if (UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Shunya/Characters/M_Drone.M_Drone"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mesh->SetMaterial(0, Material);
	}
}

void AChaserDrone::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TimeSinceLastHit += DeltaSeconds;

	const AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr;
	if (GameMode && GameMode->GetRules().IsOver())
	{
		return;
	}
	AOrbRunnerPawn* Player = Cast<AOrbRunnerPawn>(UGameplayStatics::GetPlayerPawn(this, 0));
	if (!Player)
	{
		return;
	}
	const FVector Target = Player->GetActorLocation();
	AddActorWorldOffset(ComputeSteer(GetActorLocation(), Target, Speed, DeltaSeconds));

	if (FVector::Dist2D(GetActorLocation(), Target) <= ContactRadius && CanDamage(TimeSinceLastHit, DamageCooldown))
	{
		TimeSinceLastHit = 0.f;
		if (UHealthComponent* Health = Player->GetHealth())
		{
			Health->ApplyDamage(ContactDamage);
		}
		if (USoundBase* Sound = LoadObject<USoundBase>(nullptr, TEXT("/Game/Shunya/Audio/S_Hit.S_Hit"), nullptr, LOAD_NoWarn | LOAD_Quiet))
		{
			UGameplayStatics::PlaySoundAtLocation(this, Sound, GetActorLocation());
		}
	}
}

FVector AChaserDrone::ComputeSteer(const FVector& From, const FVector& To, float Speed, float DeltaSeconds)
{
	FVector ToTarget = To - From;
	ToTarget.Z = 0.f;
	const float Distance = ToTarget.Size();
	if (Distance <= KINDA_SMALL_NUMBER || Speed <= 0.f || DeltaSeconds <= 0.f)
	{
		return FVector::ZeroVector;
	}
	const float Step = FMath::Min(Distance, Speed * DeltaSeconds);
	return ToTarget / Distance * Step;
}

bool AChaserDrone::CanDamage(float TimeSinceLastHit, float Cooldown)
{
	return TimeSinceLastHit >= Cooldown;
}
