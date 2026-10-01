// Automation tests for the HUD text.

#include "CoreMinimal.h"
#include "Game/OrbGameMode.h"
#include "Misc/AutomationTest.h"
#include "UI/OrbHUD.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace OrbHUDTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbHUDTimeTest, "ShunyaGame.UI.TimeIsShownAsMinutesAndSeconds", OrbHUDTests::Flags)
bool FOrbHUDTimeTest::RunTest(const FString& Parameters)
{
	TestEqual(TEXT("A full minute"), AOrbHUD::FormatTime(60.f), FString(TEXT("1:00")));
	TestEqual(TEXT("Seconds are zero padded"), AOrbHUD::FormatTime(9.f), FString(TEXT("0:09")));
	TestEqual(TEXT("Part seconds round up"), AOrbHUD::FormatTime(0.2f), FString(TEXT("0:01")));
	TestEqual(TEXT("Out of time"), AOrbHUD::FormatTime(0.f), FString(TEXT("0:00")));
	TestEqual(TEXT("Never negative"), AOrbHUD::FormatTime(-3.f), FString(TEXT("0:00")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbHUDBannerTest, "ShunyaGame.UI.BannerMatchesTheResult", OrbHUDTests::Flags)
bool FOrbHUDBannerTest::RunTest(const FString& Parameters)
{
	TestTrue(TEXT("No banner while playing"), AOrbHUD::FormatBanner(EOrbMatchState::Playing).IsEmpty());
	TestEqual(TEXT("Win banner"), AOrbHUD::FormatBanner(EOrbMatchState::Won), FString(TEXT("ALL ORBS RECOVERED")));
	TestEqual(TEXT("Lose banner"), AOrbHUD::FormatBanner(EOrbMatchState::Lost), FString(TEXT("SIGNAL LOST")));
	TestEqual(TEXT("Score line"), AOrbHUD::FormatScoreLine(30, 5), FString(TEXT("SCORE 30   ORBS LEFT 5")));
	TestTrue(TEXT("The game mode uses this HUD"), GetDefault<AOrbGameMode>()->HUDClass == AOrbHUD::StaticClass());
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
