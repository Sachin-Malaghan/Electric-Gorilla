"""An editor crash during a test run is reported to the agent with the exception and its own frames."""

from shunya.tools.unreal_build import parse_crash

LOG = """
[2026.10.10-14.34.02:913][571]LogAutomationController: Display: Test Started. Name={DamageIntakeAndDeath} Path={ShunyaGame.Enemy.DamageIntakeAndDeath}
[2026.10.10-14.34.07:100][571]LogWindows: Error: === Critical error: ===
[2026.10.10-14.34.07:100][571]LogWindows: Error:
[2026.10.10-14.34.07:100][571]LogWindows: Error: Fatal error!
[2026.10.10-14.34.07:100][571]LogWindows: Error:
[2026.10.10-14.34.07:100][571]LogWindows: Error: Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x00000000000001d8
[2026.10.10-14.34.07:100][571]LogWindows: Error: [Callstack] 0x00007ffd6c28d257 UnrealEditor-Engine.dll!UnknownFunction []
[2026.10.10-14.34.07:100][571]LogWindows: Error: [Callstack] 0x00000207fc66001e UnrealEditor-ShunyaGame.dll!AEnemyCharacter::TakeDamage() [C:\\wt\\Source\\ShunyaGame\\Private\\Characters\\EnemyCharacter.cpp:82]
[2026.10.10-14.34.07:100][571]LogWindows: Error: [Callstack] 0x00000207fc662095 UnrealEditor-ShunyaGame.dll!FEnemyTest::RunTest() [C:\\wt\\Source\\ShunyaGame\\Private\\Tests\\EnemyCharacterTest.cpp:138]
[2026.10.10-14.34.07:100][571]LogWindows: Error: [Callstack] 0x00007ffd704a11b6 UnrealEditor-Core.dll!UnknownFunction []
"""


def test_crash_is_summarised_with_project_frames():
    lines = parse_crash(LOG, "ShunyaGame")
    text = "\n".join(lines)
    assert "CRASHED" in lines[0] and "EXCEPTION_ACCESS_VIOLATION" in text
    assert "EnemyCharacter.cpp:82" in text and "EnemyCharacterTest.cpp:138" in text
    assert "UnrealEditor-Core.dll" not in text  # engine frames are noise when our own frames are known


def test_no_crash_no_report():
    assert parse_crash("LogAutomationController: Display: Test Completed. Result={Success}", "ShunyaGame") == []
