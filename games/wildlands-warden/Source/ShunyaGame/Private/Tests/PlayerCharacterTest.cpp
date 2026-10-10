// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Characters/PlayerCharacter.h"
#include "Components/HealthComponent.h"
#include "Components/StaminaComponent.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/StaticMeshComponent.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaPlayerTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// 1. Acceptance Criteria 1: Components and Basic Shape Assembly
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayerCharacterAssemblyTest, "ShunyaGame.Player.Assembly", ShunyaPlayerTests::Flags)
bool FPlayerCharacterAssemblyTest::RunTest(const FString& Parameters)
{
	APlayerCharacter* Player = NewObject<APlayerCharacter>();
	TestNotNull(TEXT("PlayerCharacter should be created"), Player);
	if (!Player)
	{
		return false;
	}

	TestNotNull(TEXT("CameraBoom should exist"), Player->GetCameraBoom());
	TestNotNull(TEXT("FollowCamera should exist"), Player->GetFollowCamera());
	TestNotNull(TEXT("BodyMesh should exist"), Player->GetBodyMesh());
	TestNotNull(TEXT("WeaponMesh should exist"), Player->GetWeaponMesh());
	TestNotNull(TEXT("HealthComponent should exist"), Player->GetHealthComponent());
	TestNotNull(TEXT("StaminaComponent should exist"), Player->GetStaminaComponent());

	// Check attachments
	if (Player->GetCameraBoom() && Player->GetFollowCamera())
	{
		TestTrue(TEXT("FollowCamera should be attached to CameraBoom"),
			Player->GetFollowCamera()->GetAttachParent() == Player->GetCameraBoom());
	}

	if (Player->GetBodyMesh() && Player->GetWeaponMesh())
	{
		TestTrue(TEXT("WeaponMesh should be attached to BodyMesh"),
			Player->GetWeaponMesh()->GetAttachParent() == Player->GetBodyMesh());
	}

	return true;
}

// 2. Acceptance Criteria 2: Sprint Mechanic and Stamina Drain
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayerCharacterSprintTest, "ShunyaGame.Player.Movement.Sprint", ShunyaPlayerTests::Flags)
bool FPlayerCharacterSprintTest::RunTest(const FString& Parameters)
{
	APlayerCharacter* Player = NewObject<APlayerCharacter>();
	TestNotNull(TEXT("PlayerCharacter should be created"), Player);
	if (!Player)
	{
		return false;
	}

	UStaminaComponent* Stamina = Player->GetStaminaComponent();
	TestNotNull(TEXT("StaminaComponent should be valid"), Stamina);
	if (!Stamina)
	{
		return false;
	}

	TestFalse(TEXT("Should not be sprinting initially"), Player->IsSprinting());

	// Start sprinting with full stamina
	Player->StartSprint();
	TestTrue(TEXT("Should be sprinting after StartSprint"), Player->IsSprinting());
	if (Player->GetCharacterMovement())
	{
		TestEqual(TEXT("MaxWalkSpeed should be SprintSpeed (700)"),
			Player->GetCharacterMovement()->MaxWalkSpeed,
			APlayerCharacter::SprintSpeed);
	}

	// UpdateSprint drains 20 stamina / s
	Player->UpdateSprint(1.0f);
	TestEqual(TEXT("Stamina should have dropped by 20 after 1s"), Stamina->GetStamina(), 80.0f);
	TestTrue(TEXT("Still sprinting"), Player->IsSprinting());

	// Stop sprint manually
	Player->StopSprint();
	TestFalse(TEXT("Should stop sprinting after StopSprint"), Player->IsSprinting());
	if (Player->GetCharacterMovement())
	{
		TestEqual(TEXT("MaxWalkSpeed should return to BaseWalkSpeed (400)"),
			Player->GetCharacterMovement()->MaxWalkSpeed,
			APlayerCharacter::BaseWalkSpeed);
	}

	// Deplete remaining stamina
	Stamina->ConsumeStamina(80.0f);
	TestEqual(TEXT("Stamina is 0"), Stamina->GetStamina(), 0.0f);

	// Attempting to sprint with 0 stamina should fail
	Player->StartSprint();
	TestFalse(TEXT("Cannot start sprint with 0 stamina"), Player->IsSprinting());

	// If somehow sprinting when stamina depletes, UpdateSprint drops to walk speed
	Stamina->RestoreStamina(10.0f);
	Player->StartSprint();
	TestTrue(TEXT("Started sprint with 10 stamina"), Player->IsSprinting());
	// Draining 1.0s (20 stamina) when only 10 available should fail and cancel sprint
	Player->UpdateSprint(1.0f);
	TestFalse(TEXT("Sprint should be cancelled when stamina is exhausted"), Player->IsSprinting());
	if (Player->GetCharacterMovement())
	{
		TestEqual(TEXT("MaxWalkSpeed should be BaseWalkSpeed (400) after exhaustion"),
			Player->GetCharacterMovement()->MaxWalkSpeed,
			APlayerCharacter::BaseWalkSpeed);
	}

	return true;
}

// 3. Acceptance Criteria 2: Dodge Impulse and Stamina / Cooldown Check
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayerCharacterDodgeTest, "ShunyaGame.Player.Movement.Dodge", ShunyaPlayerTests::Flags)
bool FPlayerCharacterDodgeTest::RunTest(const FString& Parameters)
{
	APlayerCharacter* Player = NewObject<APlayerCharacter>();
	TestNotNull(TEXT("PlayerCharacter should be created"), Player);
	if (!Player)
	{
		return false;
	}

	UStaminaComponent* Stamina = Player->GetStaminaComponent();
	TestNotNull(TEXT("StaminaComponent should be valid"), Stamina);
	if (!Stamina)
	{
		return false;
	}

	TestEqual(TEXT("Initial stamina is 100"), Stamina->GetStamina(), 100.0f);
	TestFalse(TEXT("Not dodging initially"), Player->IsDodging());

	// Perform dodge: costs 25 stamina
	TestTrue(TEXT("Dodge succeeds with 100 stamina"), Player->PerformDodge());
	TestEqual(TEXT("Stamina reduced by 25 to 75"), Stamina->GetStamina(), 75.0f);
	TestTrue(TEXT("IsDodging is true"), Player->IsDodging());
	TestEqual(TEXT("Dodge cooldown is 0.5s"), Player->GetDodgeCooldownRemaining(), APlayerCharacter::DodgeCooldownDuration);

	// Cannot dodge while currently dodging or on cooldown
	TestFalse(TEXT("Cannot dodge while on cooldown"), Player->PerformDodge());
	TestEqual(TEXT("Stamina remains 75"), Stamina->GetStamina(), 75.0f);

	// Advance time past dodge duration (0.3s)
	Player->UpdateDodge(0.35f);
	TestFalse(TEXT("Dodge duration ended"), Player->IsDodging());
	TestTrue(TEXT("Cooldown still remaining"), Player->GetDodgeCooldownRemaining() > 0.0f);
	TestFalse(TEXT("Still cannot dodge because cooldown is active"), Player->PerformDodge());

	// Advance past cooldown (0.5s total)
	Player->UpdateDodge(0.2f);
	TestEqual(TEXT("Cooldown finished"), Player->GetDodgeCooldownRemaining(), 0.0f);

	// Drain stamina down to 20 (< 25 required for dodge)
	Stamina->ConsumeStamina(55.0f);
	TestEqual(TEXT("Stamina is now 20"), Stamina->GetStamina(), 20.0f);

	// Dodge should fail due to insufficient stamina
	TestFalse(TEXT("Dodge fails when stamina < 25"), Player->PerformDodge());
	TestEqual(TEXT("Stamina remained 20"), Stamina->GetStamina(), 20.0f);
	TestFalse(TEXT("Player is not dodging"), Player->IsDodging());

	return true;
}

// 4. Acceptance Criteria 3: Melee Attacks (Light and Heavy) Stamina and Cooldown
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPlayerCharacterAttacksTest, "ShunyaGame.Player.Combat.Attacks", ShunyaPlayerTests::Flags)
bool FPlayerCharacterAttacksTest::RunTest(const FString& Parameters)
{
	APlayerCharacter* Player = NewObject<APlayerCharacter>();
	TestNotNull(TEXT("PlayerCharacter should be created"), Player);
	if (!Player)
	{
		return false;
	}

	UStaminaComponent* Stamina = Player->GetStaminaComponent();
	TestNotNull(TEXT("StaminaComponent should be valid"), Stamina);
	if (!Stamina)
	{
		return false;
	}

	// Initial stamina is 100
	TestEqual(TEXT("Initial stamina is 100"), Stamina->GetStamina(), 100.0f);

	// Light Attack: 15 stamina
	TestTrue(TEXT("Light attack succeeds with 100 stamina"), Player->PerformLightAttack());
	TestEqual(TEXT("Stamina reduced by 15 to 85"), Stamina->GetStamina(), 85.0f);

	// Heavy Attack: 35 stamina, 3.0s cooldown
	TestTrue(TEXT("Heavy attack succeeds with 85 stamina"), Player->PerformHeavyAttack());
	TestEqual(TEXT("Stamina reduced by 35 to 50"), Stamina->GetStamina(), 50.0f);
	TestEqual(TEXT("Heavy attack cooldown set to 3.0s"), Player->GetHeavyAttackCooldownRemaining(), APlayerCharacter::HeavyAttackCooldownDuration);

	// Heavy attack fails while on cooldown
	TestFalse(TEXT("Heavy attack fails during cooldown"), Player->PerformHeavyAttack());
	TestEqual(TEXT("Stamina remained 50 during cooldown failure"), Stamina->GetStamina(), 50.0f);

	// Light attack still works during heavy attack cooldown
	TestTrue(TEXT("Light attack works even when heavy is on cooldown"), Player->PerformLightAttack());
	TestEqual(TEXT("Stamina reduced to 35"), Stamina->GetStamina(), 35.0f);

	// Advance time by 1.5s: cooldown is 1.5s
	Player->UpdateCombatTimers(1.5f);
	TestEqual(TEXT("Heavy attack cooldown is 1.5s"), Player->GetHeavyAttackCooldownRemaining(), 1.5f);
	TestFalse(TEXT("Heavy attack still fails"), Player->PerformHeavyAttack());

	// Advance time by another 1.5s: cooldown ends
	Player->UpdateCombatTimers(1.5f);
	TestEqual(TEXT("Heavy attack cooldown is 0"), Player->GetHeavyAttackCooldownRemaining(), 0.0f);

	// Deplete stamina down to 30 (< 35 required for heavy attack)
	Stamina->ConsumeStamina(5.0f);
	TestEqual(TEXT("Stamina is 30"), Stamina->GetStamina(), 30.0f);

	TestFalse(TEXT("Heavy attack fails with insufficient stamina (30 < 35)"), Player->PerformHeavyAttack());
	TestEqual(TEXT("Stamina unchanged at 30"), Stamina->GetStamina(), 30.0f);

	// Light attack succeeds with 30 stamina (costs 15)
	TestTrue(TEXT("Light attack succeeds with 30 stamina"), Player->PerformLightAttack());
	TestEqual(TEXT("Stamina is now 15"), Stamina->GetStamina(), 15.0f);

	// Another light attack uses remaining 15 stamina
	TestTrue(TEXT("Light attack succeeds with 15 stamina"), Player->PerformLightAttack());
	TestEqual(TEXT("Stamina is 0"), Stamina->GetStamina(), 0.0f);

	// Light attack fails with 0 stamina
	TestFalse(TEXT("Light attack fails with 0 stamina"), Player->PerformLightAttack());
	TestEqual(TEXT("Stamina remains 0"), Stamina->GetStamina(), 0.0f);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
