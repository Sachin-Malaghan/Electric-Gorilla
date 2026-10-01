// Automation tests for the Orb Runner match rules.

#include "CoreMinimal.h"
#include "Game/OrbRules.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace OrbRulesTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbRulesCollectAllWinsTest, "ShunyaGame.Rules.CollectingEveryOrbWins", OrbRulesTests::Flags)
bool FOrbRulesCollectAllWinsTest::RunTest(const FString& Parameters)
{
	FOrbRules Rules;
	Rules.Start(3);
	TestEqual(TEXT("Timer starts at the time limit"), Rules.TimeRemaining, 60.f);
	Rules.CollectOrb(10);
	Rules.CollectOrb(10);
	TestEqual(TEXT("Score adds up"), Rules.Score, 20);
	TestTrue(TEXT("Still playing with one orb left"), Rules.State == EOrbMatchState::Playing);
	Rules.CollectOrb(10);
	TestTrue(TEXT("Collecting the last orb wins"), Rules.State == EOrbMatchState::Won);
	TestEqual(TEXT("Final score"), Rules.Score, 30);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbRulesTimeoutLosesTest, "ShunyaGame.Rules.RunningOutOfTimeLoses", OrbRulesTests::Flags)
bool FOrbRulesTimeoutLosesTest::RunTest(const FString& Parameters)
{
	FOrbRules Rules;
	Rules.Start(2);
	Rules.Tick(59.f);
	TestEqual(TEXT("One second left"), Rules.TimeRemaining, 1.f);
	TestTrue(TEXT("Still playing"), Rules.State == EOrbMatchState::Playing);
	Rules.Tick(5.f);
	TestEqual(TEXT("Timer never goes below zero"), Rules.TimeRemaining, 0.f);
	TestTrue(TEXT("Timeout loses"), Rules.State == EOrbMatchState::Lost);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbRulesFrozenAfterEndTest, "ShunyaGame.Rules.NothingChangesAfterTheMatchEnds", OrbRulesTests::Flags)
bool FOrbRulesFrozenAfterEndTest::RunTest(const FString& Parameters)
{
	FOrbRules Rules;
	Rules.Start(1);
	Rules.CollectOrb(10);
	Rules.CollectOrb(10);
	Rules.Tick(100.f);
	Rules.PlayerDied();
	TestEqual(TEXT("Score is frozen"), Rules.Score, 10);
	TestTrue(TEXT("A win stays a win"), Rules.State == EOrbMatchState::Won);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOrbRulesPlayerDeathLosesTest, "ShunyaGame.Rules.PlayerDeathLoses", OrbRulesTests::Flags)
bool FOrbRulesPlayerDeathLosesTest::RunTest(const FString& Parameters)
{
	FOrbRules Rules;
	Rules.Start(4);
	Rules.CollectOrb(10);
	Rules.PlayerDied();
	TestTrue(TEXT("Death loses the match"), Rules.State == EOrbMatchState::Lost);
	Rules.CollectOrb(10);
	TestEqual(TEXT("No score after losing"), Rules.Score, 10);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
