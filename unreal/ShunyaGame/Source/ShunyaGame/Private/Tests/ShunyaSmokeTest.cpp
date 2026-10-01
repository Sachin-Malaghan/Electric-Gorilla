// Reference automation test: shows how tests are declared in this project.
// Tests run headless, so they must not need rendering or a loaded map.

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "ShunyaGameMode.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace ShunyaTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FShunyaSmokeGameModeClassTest, "ShunyaGame.Smoke.GameModeClassExists", ShunyaTests::Flags)

bool FShunyaSmokeGameModeClassTest::RunTest(const FString& Parameters)
{
	const UClass* GameModeClass = AShunyaGameMode::StaticClass();
	TestNotNull(TEXT("AShunyaGameMode is registered with the reflection system"), GameModeClass);
	TestTrue(TEXT("AShunyaGameMode derives from AGameModeBase"), GameModeClass && GameModeClass->IsChildOf(AGameModeBase::StaticClass()));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
