"""Scripts for the deterministic provider: the first milestone (spec 48), played by rote.

These are NOT agents reasoning - they are a fixed screenplay for "create a simple Unreal
health component" that drives the real pipeline (real worktree, real compiler, real
automation tests, real review/QA/approval gates) without an LLM. It exists so the
platform can be demonstrated, tested and debugged offline and for free. With
`inject_compile_error` the programmer's first attempt contains a typo so the
compile-error -> parse -> diagnose -> fix loop is exercised for real.

Any other feature request is declined with a clear message: use the Anthropic provider.
"""

from __future__ import annotations

import re

from shunya.core.models.base import ModelProviderError
from shunya.core.models.scripted_provider import Script, ScriptContext, ScriptStep, call, calls

HEADER_PATH = "Source/ShunyaGame/Public/Components/HealthComponent.h"
SOURCE_PATH = "Source/ShunyaGame/Private/Components/HealthComponent.cpp"
TESTS_PATH = "Source/ShunyaGame/Private/Tests/HealthComponentTests.cpp"
TEST_FILTER = "ShunyaGame.Health"

HEADER = '''// Reusable health pool for any actor. Server-authoritative and replicated.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"

#include "HealthComponent.generated.h"

class UHealthComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnHealthChanged, UHealthComponent*, Component, float, NewHealth, float, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDeath, UHealthComponent*, Component);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnDeathNative, UHealthComponent*);

UCLASS(ClassGroup = (Shunya), meta = (BlueprintSpawnableComponent))
class SHUNYAGAME_API UHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UHealthComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Applies damage on the authority. Returns the damage actually applied (0 if dead, invalid, or not authoritative). */
	UFUNCTION(BlueprintCallable, Category = "Health")
	float ApplyDamage(float Amount);

	/** Restores health on the authority, up to MaxHealth. Has no effect once dead. Returns the amount restored. */
	UFUNCTION(BlueprintCallable, Category = "Health")
	float Heal(float Amount);

	UFUNCTION(BlueprintPure, Category = "Health")
	float GetHealth() const { return Health; }

	UFUNCTION(BlueprintPure, Category = "Health")
	float GetMaxHealth() const { return MaxHealth; }

	UFUNCTION(BlueprintPure, Category = "Health")
	bool IsDead() const { return bIsDead; }

	UPROPERTY(BlueprintAssignable, Category = "Health")
	FOnHealthChanged OnHealthChanged;

	/** Fires exactly once, when health first reaches zero. */
	UPROPERTY(BlueprintAssignable, Category = "Health")
	FOnDeath OnDeath;

	/** Native counterpart of OnDeath for C++ listeners. */
	FOnDeathNative OnDeathNative;

protected:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Replicated, Category = "Health", meta = (ClampMin = "1.0"))
	float MaxHealth = 100.f;

	UPROPERTY(BlueprintReadOnly, ReplicatedUsing = OnRep_Health, Category = "Health")
	float Health = 100.f;

	UPROPERTY(BlueprintReadOnly, Replicated, Category = "Health")
	bool bIsDead = false;

	UFUNCTION()
	void OnRep_Health(float OldHealth);

private:
	/** True on the server, and for ownerless components (unit tests). */
	bool CanMutate() const;
};
'''

SOURCE = '''// Reusable health pool for any actor. Server-authoritative and replicated.

#include "Components/HealthComponent.h"

#include "GameFramework/Actor.h"
#include "Net/UnrealNetwork.h"

UHealthComponent::UHealthComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
	Health = MaxHealth;
}

void UHealthComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UHealthComponent, MaxHealth);
	DOREPLIFETIME(UHealthComponent, Health);
	DOREPLIFETIME(UHealthComponent, bIsDead);
}

bool UHealthComponent::CanMutate() const
{
	const AActor* Owner = GetOwner();
	return Owner == nullptr || Owner->HasAuthority();
}

float UHealthComponent::ApplyDamage(float Amount)
{
	if (!CanMutate() || bIsDead || Amount <= 0.f)
	{
		return 0.f;
	}
	const float OldHealth = Health;
	Health = FMath::Clamp(Health - Amount, 0.f, MaxHealth);
	const float Applied = OldHealth - Health;
	if (Applied > 0.f)
	{
		OnHealthChanged.Broadcast(this, Health, -Applied);
	}
	if (Health <= 0.f && !bIsDead)
	{
		bIsDead = true;
		OnDeath.Broadcast(this);
		OnDeathNative.Broadcast(this);
	}
	return Applied;
}

float UHealthComponent::Heal(float Amount)
{
	if (!CanMutate() || bIsDead || Amount <= 0.f)
	{
		return 0.f;
	}
	const float OldHealth = Health;
	Health = FMath::Clamp(Health + Amount, 0.f, __MAX__);
	const float Restored = Health - OldHealth;
	if (Restored > 0.f)
	{
		OnHealthChanged.Broadcast(this, Health, Restored);
	}
	return Restored;
}

void UHealthComponent::OnRep_Health(float OldHealth)
{
	OnHealthChanged.Broadcast(this, Health, Health - OldHealth);
}
'''

TESTS = '''// Automation tests for UHealthComponent - one per acceptance criterion.

#include "Components/HealthComponent.h"
#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace HealthTests
{
	constexpr EAutomationTestFlags Flags = EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter;

	UHealthComponent* MakeComponent()
	{
		return NewObject<UHealthComponent>(GetTransientPackage());
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDefaultsTest, "ShunyaGame.Health.DefaultsTo100", HealthTests::Flags)
bool FHealthDefaultsTest::RunTest(const FString& Parameters)
{
	const UHealthComponent* Health = HealthTests::MakeComponent();
	TestEqual(TEXT("Health defaults to 100"), Health->GetHealth(), 100.f);
	TestEqual(TEXT("MaxHealth defaults to 100"), Health->GetMaxHealth(), 100.f);
	TestFalse(TEXT("A new component is alive"), Health->IsDead());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDamageClampTest, "ShunyaGame.Health.DamageCannotGoBelowZero", HealthTests::Flags)
bool FHealthDamageClampTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	TestEqual(TEXT("30 damage is applied in full"), Health->ApplyDamage(30.f), 30.f);
	TestEqual(TEXT("Health is 70 after 30 damage"), Health->GetHealth(), 70.f);
	TestEqual(TEXT("Negative damage is ignored"), Health->ApplyDamage(-50.f), 0.f);
	TestEqual(TEXT("Health unchanged by negative damage"), Health->GetHealth(), 70.f);
	TestEqual(TEXT("Overkill damage only applies what is left"), Health->ApplyDamage(500.f), 70.f);
	TestEqual(TEXT("Health never goes below 0"), Health->GetHealth(), 0.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthDeathOnceTest, "ShunyaGame.Health.DeathEventFiresOnce", HealthTests::Flags)
bool FHealthDeathOnceTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	int32 DeathEvents = 0;
	Health->OnDeathNative.AddLambda([&DeathEvents](UHealthComponent*) { ++DeathEvents; });
	Health->ApplyDamage(60.f);
	TestEqual(TEXT("No death event while alive"), DeathEvents, 0);
	Health->ApplyDamage(60.f);
	TestTrue(TEXT("Component is dead at zero health"), Health->IsDead());
	TestEqual(TEXT("Death event fired"), DeathEvents, 1);
	Health->ApplyDamage(10.f);
	Health->ApplyDamage(10.f);
	TestEqual(TEXT("Death event does not fire again"), DeathEvents, 1);
	TestEqual(TEXT("Healing a dead component does nothing"), Health->Heal(50.f), 0.f);
	TestEqual(TEXT("Death event still fired exactly once"), DeathEvents, 1);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthHealClampTest, "ShunyaGame.Health.HealClampsToMax", HealthTests::Flags)
bool FHealthHealClampTest::RunTest(const FString& Parameters)
{
	UHealthComponent* Health = HealthTests::MakeComponent();
	Health->ApplyDamage(40.f);
	TestEqual(TEXT("Heal restores only up to max"), Health->Heal(100.f), 40.f);
	TestEqual(TEXT("Health is capped at MaxHealth"), Health->GetHealth(), Health->GetMaxHealth());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHealthReplicationTest, "ShunyaGame.Health.ReplicatedForMultiplayer", HealthTests::Flags)
bool FHealthReplicationTest::RunTest(const FString& Parameters)
{
	const UHealthComponent* Health = HealthTests::MakeComponent();
	TestTrue(TEXT("Component replicates by default"), Health->GetIsReplicated());
	const FProperty* HealthProperty = FindFProperty<FProperty>(UHealthComponent::StaticClass(), TEXT("Health"));
	const FProperty* DeadProperty = FindFProperty<FProperty>(UHealthComponent::StaticClass(), TEXT("bIsDead"));
	TestTrue(TEXT("Health is a replicated property"), HealthProperty && HealthProperty->HasAnyPropertyFlags(CPF_Net));
	TestTrue(TEXT("Health has a RepNotify"), HealthProperty && HealthProperty->HasAnyPropertyFlags(CPF_RepNotify));
	TestTrue(TEXT("bIsDead is a replicated property"), DeadProperty && DeadProperty->HasAnyPropertyFlags(CPF_Net));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
'''

ACCEPTANCE = [
    "Health defaults to 100",
    "Damage cannot reduce health below 0",
    "Death event fires exactly once",
    "Component works in multiplayer: state is replicated and only changed on the authority",
]

_EVIDENCE = [
    ("default", "ShunyaGame.Health.DefaultsTo100", "asserts GetHealth() == 100 and GetMaxHealth() == 100 on a new component"),
    ("below", "ShunyaGame.Health.DamageCannotGoBelowZero", "applies 500 damage at 70 health and asserts health == 0 and applied == 70"),
    ("death", "ShunyaGame.Health.DeathEventFiresOnce", "counts OnDeathNative broadcasts across repeated lethal damage and asserts the count is 1"),
    ("multiplayer", "ShunyaGame.Health.ReplicatedForMultiplayer", "asserts GetIsReplicated() and CPF_Net on Health and bIsDead, CPF_RepNotify on Health"),
]


def _report_fields(ctx: ScriptContext) -> set[str]:
    for t in ctx.tools:
        if t.name == "submit_report":
            return set(t.input_schema.get("properties", {}))
    return set()


def _submit(**report) -> ScriptStep:
    return call("submit_report", **report)


def _is_health(text: str) -> bool:
    return "health" in text.lower()


def _decline() -> None:
    raise ModelProviderError(
        "The scripted demo provider only knows the 'health component' milestone. "
        "Set SHUNYA_MODEL_PROVIDER=anthropic to have real agents handle any request."
    )


def director(ctx: ScriptContext) -> ScriptStep:
    # look only at the owner's request: retrieved project docs also mention health
    if not _is_health(ctx.section("Feature request from the studio owner")):
        _decline()
    if not ctx.called("list_dir"):
        return call("list_dir", path="Source", depth=3)
    return _submit(
        objective="Give any actor a reusable, multiplayer-safe health pool so damage, death and healing behave the same everywhere.",
        scope_in=["A UHealthComponent actor component", "Damage, healing and a death event", "Replication of health state", "Automation tests"],
        scope_out=["Damage types, armour or resistances", "UI / health bars", "Respawning"],
        risks=["Death must fire exactly once even under repeated or overkill damage", "State must only change on the server"],
        summary="Add a small, replicated health component with tests; no gameplay built on top of it yet.",
    )


def producer(ctx: ScriptContext) -> ScriptStep:
    if not _is_health(ctx.section("Feature request")):
        _decline()
    if not ctx.called("list_dir"):
        return calls(("list_dir", {"path": "Source/ShunyaGame", "depth": 3}), ("search_files", {"pattern": r"class \w+_API", "path": "Source"}))
    return _submit(
        epic_title="Health component",
        summary="One implementation task: a replicated UHealthComponent with automation tests under ShunyaGame.Health.",
        tasks=[
            {
                "title": "Implement health component",
                "description": (
                    "Add UHealthComponent (UActorComponent) to the ShunyaGame module under Public/Components and Private/Components. "
                    "It holds Health and MaxHealth, exposes ApplyDamage/Heal/GetHealth/IsDead, broadcasts a death event, and replicates its state. "
                    "Add automation tests under ShunyaGame.Health in Private/Tests."
                ),
                "type": "IMPLEMENTATION",
                "priority": "HIGH",
                "acceptance_criteria": ACCEPTANCE,
                "depends_on": [],
                "test_filter": TEST_FILTER,
            }
        ],
        open_questions=[],
    )


def _plan_review(ctx: ScriptContext) -> ScriptStep:
    if not ctx.called("read_file"):
        return call("read_file", path="Source/ShunyaGame/ShunyaGame.Build.cs")
    return _submit(
        feasible=True,
        concerns=[],
        suggestions=["Expose a native (non-dynamic) death delegate so C++ tests can count broadcasts with a lambda."],
        summary="Feasible as one task. The module already depends on Engine and NetCore, so replication needs no Build.cs change; every criterion is testable headless with NewObject.",
    )


def make_programmer(inject_compile_error: bool) -> Script:
    def programmer(ctx: ScriptContext) -> ScriptStep:
        if "feasible" in _report_fields(ctx):
            return _plan_review(ctx)
        ex = ctx.exchanges
        if not ctx.called("list_dir"):
            return calls(
                ("list_dir", {"path": "Source/ShunyaGame", "depth": 4}),
                ("read_file", {"path": "Source/ShunyaGame/ShunyaGame.Build.cs"}),
                text="Looking at the module layout and its dependencies first.",
            )
        if len(ctx.called("read_file")) < 2:
            return call("read_file", path="Source/ShunyaGame/Private/Tests/ShunyaSmokeTest.cpp")
        listing = ctx.called("list_dir")[0].result
        already_there = "HealthComponent.h" in listing
        writes = [i for i, e in enumerate(ex) if e.name in ("create_file", "patch_file") and not e.is_error]
        compiles = [i for i, e in enumerate(ex) if e.name == "compile_project"]
        tests = [i for i, e in enumerate(ex) if e.name == "run_automation_tests"]
        if not already_there and not ctx.called("create_file"):
            first_attempt = not ctx.section("Feedback you must address (from review / build / QA / humans)")
            source = SOURCE.replace("__MAX__", "MaxHeath" if inject_compile_error and first_attempt else "MaxHealth")
            return calls(
                ("create_file", {"path": HEADER_PATH, "content": HEADER}),
                ("create_file", {"path": SOURCE_PATH, "content": source}),
                ("create_file", {"path": TESTS_PATH, "content": TESTS}),
            )
        last_write = writes[-1] if writes else -1
        if not compiles or compiles[-1] < last_write:
            return call("compile_project")
        compile_result = ex[compiles[-1]]
        if compile_result.is_error:
            if "SKIPPED" in compile_result.result:
                return _submit(
                    summary="Implemented UHealthComponent with tests, but no Unreal Engine is configured here so nothing was compiled or run.",
                    files_changed=[HEADER_PATH, SOURCE_PATH, TESTS_PATH], compiled=False, tests_passed=False, blocked=False, blocked_reason="",
                    notes="UNVERIFIED: build and tests were skipped (no engine).",
                )
            if "MaxHeath" in compile_result.result and not ctx.called("patch_file"):
                return calls(
                    ("patch_file", {"path": SOURCE_PATH, "old_text": "0.f, MaxHeath);", "new_text": "0.f, MaxHealth);"}),
                    text="The compiler reports 'MaxHeath' as undeclared in Heal() - a typo for MaxHealth.",
                )
            return _submit(
                summary="Could not get the health component to compile.", files_changed=[HEADER_PATH, SOURCE_PATH, TESTS_PATH],
                compiled=False, tests_passed=False, blocked=True, blocked_reason=compile_result.result[:600], notes="",
            )
        if not tests or tests[-1] < compiles[-1]:
            return call("run_automation_tests", filter=TEST_FILTER)
        tests_ok = not ex[tests[-1]].is_error
        return _submit(
            summary=(
                "Added UHealthComponent: Health/MaxHealth default to 100, ApplyDamage clamps at 0 and reports damage applied, "
                "OnDeath/OnDeathNative fire once when health first reaches 0, Heal clamps to MaxHealth and is ignored when dead. "
                "State replicates (Health with RepNotify) and only changes on the authority."
            ),
            files_changed=[HEADER_PATH, SOURCE_PATH, TESTS_PATH], compiled=True, tests_passed=tests_ok,
            blocked=not tests_ok, blocked_reason="" if tests_ok else ex[tests[-1]].result[:600],
            notes="No Build.cs change needed: Engine and NetCore were already dependencies. Five tests under ShunyaGame.Health.",
        )

    return programmer


def reviewer(ctx: ScriptContext) -> ScriptStep:
    if not ctx.called("git_diff"):
        return calls(("git_diff", {"stat": True}), ("git_diff", {"stat": False}))
    if not ctx.called("read_file"):
        return calls(("read_file", {"path": SOURCE_PATH}), ("read_file", {"path": TESTS_PATH}))
    source = ctx.called("read_file")[0].result
    findings = []
    if "CanMutate" not in source or "bIsDead" not in source:
        findings.append({"severity": "BLOCKER", "file": SOURCE_PATH, "line": 1, "comment": "Authority check or death latch missing."})
    if findings:
        return _submit(verdict="CHANGES_REQUESTED", summary="Core behaviour is missing.", findings=findings)
    return _submit(
        verdict="APPROVE",
        summary="Matches the acceptance criteria: defaults, clamping, single death broadcast guarded by bIsDead, authority-gated mutation, replicated state with RepNotify. Tests assert each criterion.",
        findings=[{"severity": "NIT", "file": HEADER_PATH, "line": 30, "comment": "Consider a SetMaxHealth API later; not required by this task."}],
    )


def qa(ctx: ScriptContext) -> ScriptStep:
    m = re.search(r"filter `([\w.]+)`", ctx.brief)
    test_filter = m.group(1) if m else TEST_FILTER
    if not ctx.called("run_automation_tests"):
        return call("run_automation_tests", filter=test_filter)
    if not ctx.called("read_file"):
        return call("read_file", path=TESTS_PATH)
    run = ctx.last("run_automation_tests")
    assert run is not None
    criteria_text = [re.sub(r"^\d+\.\s*", "", line).strip() for line in ctx.section("Acceptance criteria").splitlines() if line.strip()]
    skipped = "SKIPPED" in run.result
    passed_tests = set(re.findall(r"\[PASS\] (\S+)", run.result))
    failed = re.findall(r"\[FAIL\] (\S+)(?: - (.*))?", run.result)
    criteria = []
    for text in criteria_text:
        key, test, what = next((e for e in _EVIDENCE if e[0] in text.lower()), ("", "", ""))
        met = bool(test) and (test in passed_tests or skipped)
        evidence = f"{test}: {what}" if test else "no test covers this criterion"
        if skipped and test:
            evidence += " (read in source only - tests were not run: no engine)"
        criteria.append({"criterion": text, "met": met, "evidence": evidence})
    if not run.is_error or skipped:
        ok = all(c["met"] for c in criteria)
        return _submit(
            verdict="PASS" if ok else "FAIL",
            summary=("All acceptance criteria are covered by passing automation tests." if not skipped else "Static inspection only: Unreal is not available, tests were NOT run.")
            if ok else "Some acceptance criteria have no passing test.",
            criteria=criteria,
            defects=[] if ok else [{"title": f"No passing test for: {c['criterion']}", "severity": "HIGH", "test": "", "expected": "a passing test", "actual": c["evidence"]} for c in criteria if not c["met"]],
        )
    return _submit(
        verdict="FAIL",
        summary=f"{len(failed)} automation test(s) failed.",
        criteria=criteria,
        defects=[{"title": f"{name} fails", "severity": "HIGH", "test": name, "expected": "test passes", "actual": msg or "failed"} for name, msg in failed]
        or [{"title": "Test run did not pass", "severity": "HIGH", "test": test_filter, "expected": "PASSED", "actual": run.result[:300]}],
    )


def demo_scripts(*, inject_compile_error: bool = True) -> dict[str, Script]:
    return {
        "director": director,
        "producer": producer,
        "programmer": make_programmer(inject_compile_error),
        "reviewer": reviewer,
        "qa": qa,
    }
