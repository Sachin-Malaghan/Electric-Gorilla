// A collectible orb.

#include "Pickups/OrbCollectible.h"

#include "Animation/SpinBobComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Game/OrbGameMode.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Player/OrbRunnerPawn.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"

AOrbCollectible::AOrbCollectible()
{
	PrimaryActorTick.bCanEverTick = false;

	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	Trigger->InitSphereRadius(70.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Trigger->SetGenerateOverlapEvents(true);
	RootComponent = Trigger;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Trigger);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetRelativeScale3D(FVector(0.6f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded())
	{
		Mesh->SetStaticMesh(SphereMesh.Object);
	}

	Glow = CreateDefaultSubobject<UPointLightComponent>(TEXT("Glow"));
	Glow->SetupAttachment(Trigger);
	Glow->SetIntensity(3000.f);
	Glow->SetAttenuationRadius(450.f);
	Glow->SetLightColor(FLinearColor(0.2f, 0.9f, 1.f));
	Glow->SetCastShadows(false);

	SpinBob = CreateDefaultSubobject<USpinBobComponent>(TEXT("SpinBob"));
}

void AOrbCollectible::BeginPlay()
{
	Super::BeginPlay();
	if (UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Shunya/Props/M_Orb.M_Orb"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		Mesh->SetMaterial(0, Material);
	}
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AOrbCollectible::HandleOverlap);
	if (AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr)
	{
		GameMode->RegisterOrb();
	}
}

void AOrbCollectible::HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (bCollected || !Cast<AOrbRunnerPawn>(OtherActor))
	{
		return;
	}
	bCollected = true;
	if (AOrbGameMode* GameMode = GetWorld() ? GetWorld()->GetAuthGameMode<AOrbGameMode>() : nullptr)
	{
		GameMode->NotifyOrbCollected(Value);
	}
	if (USoundBase* Sound = LoadObject<USoundBase>(nullptr, TEXT("/Game/Shunya/Audio/S_Pickup.S_Pickup"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		UGameplayStatics::PlaySoundAtLocation(this, Sound, GetActorLocation());
	}
	Destroy();
}
