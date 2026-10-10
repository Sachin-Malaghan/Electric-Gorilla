// Copyright Epic Games, Inc. All Rights Reserved.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "SHUDCombatHUD.h"
#include "ShunyaCombatGameMode.h"
#include "ShunyaCombatTypes.h"
#include "UObject/Package.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaHUDTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

// 1. HUD Initialization and Class Hierarchy
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHUDInitializationTest, "ShunyaGame.HUD.Initialization", ShunyaHUDTests::Flags)
bool FHUDInitializationTest::RunTest(const FString& Parameters)
{
	const UClass* HUDClass = ASHUDCombatHUD::StaticClass();
	TestNotNull(TEXT("ASHUDCombatHUD is registered with reflection system"), HUDClass);
	TestTrue(TEXT("ASHUDCombatHUD derives from AHUD"), HUDClass && HUDClass->IsChildOf(AHUD::StaticClass()));

	ASHUDCombatHUD* HUD = NewObject<ASHUDCombatHUD>(GetTransientPackage(), ASHUDCombatHUD::StaticClass());
	TestNotNull(TEXT("ASHUDCombatHUD instance successfully created via NewObject"), HUD);

	// Verify GameMode default HUDClass is ASHUDCombatHUD
	AShunyaCombatGameMode* GameMode = NewObject<AShunyaCombatGameMode>(GetTransientPackage(), AShunyaCombatGameMode::StaticClass());
	TestNotNull(TEXT("AShunyaCombatGameMode instance created"), GameMode);
	TestEqual(TEXT("GameMode HUDClass is ASHUDCombatHUD"), GameMode->HUDClass, TSubclassOf<AHUD>(ASHUDCombatHUD::StaticClass()));

	return true;
}

// 2. Health and Stamina Bar Data Formatting Helpers
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHUDVitalsFormattingTest, "ShunyaGame.HUD.VitalsFormatting", ShunyaHUDTests::Flags)
bool FHUDVitalsFormattingTest::RunTest(const FString& Parameters)
{
	// HP formatting
	TestEqual(TEXT("Full HP format"), ASHUDCombatHUD::FormatHealthString(100.0f, 100.0f), TEXT("HP: 100 / 100"));
	TestEqual(TEXT("Partial HP format"), ASHUDCombatHUD::FormatHealthString(45.4f, 100.0f), TEXT("HP: 45 / 100"));
	TestEqual(TEXT("Zero HP format"), ASHUDCombatHUD::FormatHealthString(0.0f, 100.0f), TEXT("HP: 0 / 100"));
	TestEqual(TEXT("Clamped negative HP format"), ASHUDCombatHUD::FormatHealthString(-15.0f, 100.0f), TEXT("HP: 0 / 100"));

	// Stamina formatting
	TestEqual(TEXT("Full Stamina format"), ASHUDCombatHUD::FormatStaminaString(100.0f, 100.0f), TEXT("STAMINA: 100 / 100"));
	TestEqual(TEXT("Partial Stamina format"), ASHUDCombatHUD::FormatStaminaString(25.0f, 100.0f), TEXT("STAMINA: 25 / 100"));
	TestEqual(TEXT("Zero Stamina format"), ASHUDCombatHUD::FormatStaminaString(0.0f, 100.0f), TEXT("STAMINA: 0 / 100"));

	// Surviving Health format (Victory screen)
	TestEqual(TEXT("Surviving HP format"), ASHUDCombatHUD::FormatSurvivingHealthString(75.0f, 100.0f), TEXT("SURVIVING HEALTH: 75 / 100"));

	// Color verification
	const FLinearColor FullHealthColor = ASHUDCombatHUD::GetHealthBarColor(1.0f);
	TestTrue(TEXT("Health bar is green at full HP"), FullHealthColor.G > FullHealthColor.R);

	const FLinearColor LowHealthColor = ASHUDCombatHUD::GetHealthBarColor(0.1f);
	TestTrue(TEXT("Health bar is red-shifted when < 30%"), LowHealthColor.R > LowHealthColor.G);

	const FLinearColor StaminaColor = ASHUDCombatHUD::GetStaminaBarColor();
	TestTrue(TEXT("Stamina color has strong yellow component (R and G high)"), StaminaColor.R > 0.8f && StaminaColor.G > 0.6f);

	return true;
}

// 3. Wave and Score Data Formatting Helpers
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHUDWaveScoreFormattingTest, "ShunyaGame.HUD.WaveScoreFormatting", ShunyaHUDTests::Flags)
bool FHUDWaveScoreFormattingTest::RunTest(const FString& Parameters)
{
	// Wave formatting
	TestEqual(TEXT("Wave 1 of 3 format"), ASHUDCombatHUD::FormatWaveString(1, 3), TEXT("WAVE: 1 / 3"));
	TestEqual(TEXT("Wave 2 of 3 format"), ASHUDCombatHUD::FormatWaveString(2, 3), TEXT("WAVE: 2 / 3"));
	TestEqual(TEXT("Wave 3 of 3 format"), ASHUDCombatHUD::FormatWaveString(3, 3), TEXT("WAVE: 3 / 3"));

	// Score formatting
	TestEqual(TEXT("Zero score format"), ASHUDCombatHUD::FormatScoreString(0), TEXT("SCORE: 00000"));
	TestEqual(TEXT("Positive score format"), ASHUDCombatHUD::FormatScoreString(300), TEXT("SCORE: 00300"));
	TestEqual(TEXT("High score format"), ASHUDCombatHUD::FormatScoreString(12500), TEXT("SCORE: 12500"));

	// Enemies remaining formatting
	TestEqual(TEXT("Enemies remaining format"), ASHUDCombatHUD::FormatEnemiesRemainingString(5), TEXT("ENEMIES: 5 REMAINING"));

	// Time elapsed formatting
	TestEqual(TEXT("Time 0s format"), ASHUDCombatHUD::FormatTimeString(0.0f), TEXT("TIME: 00:00"));
	TestEqual(TEXT("Time 84s format"), ASHUDCombatHUD::FormatTimeString(84.0f), TEXT("TIME: 01:24"));

	// Inter-wave messages
	TestEqual(TEXT("Wave cleared announcement format"), ASHUDCombatHUD::FormatWaveClearedString(2), TEXT("WAVE 2 CLEARED!"));
	TestEqual(TEXT("Next wave countdown format"), ASHUDCombatHUD::FormatNextWaveCountdownString(2.5f), TEXT("NEXT WAVE IN: 2.5s"));

	return true;
}

// 4. End Screens (Game Over & Victory) Text Banners and Restart Prompt
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHUDEndScreensFormattingTest, "ShunyaGame.HUD.EndScreensFormatting", ShunyaHUDTests::Flags)
bool FHUDEndScreensFormattingTest::RunTest(const FString& Parameters)
{
	// Victory screen banners
	TestTrue(TEXT("Victory banner contains VICTORY"), ASHUDCombatHUD::VictoryBannerText.Contains(TEXT("VICTORY")));
	TestTrue(TEXT("Victory restart prompt mentions R key"), ASHUDCombatHUD::RestartPromptVictoryText.Contains(TEXT("R")));
	TestEqual(TEXT("Clear time format"), ASHUDCombatHUD::FormatClearTimeString(95.0f), TEXT("CLEAR TIME: 01:35"));

	// Game Over screen banners
	TestTrue(TEXT("Game over banner contains GAME OVER"), ASHUDCombatHUD::GameOverBannerText.Contains(TEXT("GAME OVER")));
	TestTrue(TEXT("Game over restart prompt mentions R key"), ASHUDCombatHUD::RestartPromptGameOverText.Contains(TEXT("R")));
	TestEqual(TEXT("Defeated wave format"), ASHUDCombatHUD::FormatDefeatedWaveString(2, 3), TEXT("DEFEATED ON WAVE: 2 / 3"));
	TestEqual(TEXT("Enemies defeated format"), ASHUDCombatHUD::FormatEnemiesDefeatedString(8), TEXT("ENEMIES DEFEATED: 8"));

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
