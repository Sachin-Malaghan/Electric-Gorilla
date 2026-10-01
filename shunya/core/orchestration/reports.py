"""Structured report schemas each role must submit (spec 10: structured payloads are authoritative)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DirectorBrief(BaseModel):
    objective: str = Field(description="What the player/game gains, in one or two sentences")
    scope_in: list[str] = Field(description="What this feature includes")
    scope_out: list[str] = Field(description="What is explicitly not part of it")
    risks: list[str] = Field(description="Product or technical risks worth flagging")
    summary: str


class PlannedTask(BaseModel):
    title: str
    description: str = Field(description="What to build and where, concretely enough for an engineer to start")
    type: Literal["IMPLEMENTATION", "DESIGN", "DOCUMENTATION", "QA"] = "IMPLEMENTATION"
    track: Literal["code", "doc", "content"] = Field(default="code", description="code = C++ change (compiled and tested); doc = documents under Docs/; content = Unreal assets made with the content tools")
    assignee_capability: str = Field(default="programmer", description="Capability of the employee who does it - must be one from the roster")
    reviewer_capability: str = Field(default="reviewer", description="Capability of the employee who reviews it - a lead, never the assignee")
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    acceptance_criteria: list[str] = Field(description="Independently verifiable criteria; each should be checkable by an automated test", min_length=1)
    depends_on: list[int] = Field(description="Zero-based indexes of tasks in this plan that must be DONE first")
    test_filter: str = Field(description="Unreal automation test path prefix that will verify this task, e.g. ShunyaGame.Health")


class FeaturePlan(BaseModel):
    epic_title: str
    summary: str
    tasks: list[PlannedTask] = Field(min_length=1, max_length=40)
    open_questions: list[str]


class PlanReview(BaseModel):
    feasible: bool
    concerns: list[str]
    suggestions: list[str]
    summary: str


class ImplementationReport(BaseModel):
    summary: str = Field(description="What you implemented and how it satisfies the acceptance criteria")
    files_changed: list[str]
    compiled: bool = Field(description="True only if compile_project returned PASSED after your last edit")
    tests_passed: bool = Field(description="True only if run_automation_tests returned PASSED after your last edit")
    blocked: bool = Field(description="True if you could not complete the task")
    blocked_reason: str = Field(description="Why you are blocked, or empty")
    notes: str = Field(description="Anything the reviewer or QA should know (trade-offs, config changes needed, follow-ups)")


class WorkReport(BaseModel):
    """Report for document and content work."""

    summary: str = Field(description="What you produced and how it satisfies the acceptance criteria")
    files_changed: list[str]
    assets: list[str] = Field(description="Unreal assets created or changed, by name (empty for documents)")
    blocked: bool = Field(description="True if you could not complete the task")
    blocked_reason: str
    notes: str = Field(description="Anything the reviewer should know")


class ReviewFinding(BaseModel):
    severity: Literal["BLOCKER", "MAJOR", "MINOR", "NIT"]
    file: str
    line: int
    comment: str


class ReviewReport(BaseModel):
    verdict: Literal["APPROVE", "CHANGES_REQUESTED"]
    summary: str
    findings: list[ReviewFinding]


class CriterionResult(BaseModel):
    criterion: str
    met: bool
    evidence: str = Field(description="The test name / log line / code location that demonstrates this")


class Defect(BaseModel):
    title: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    test: str
    expected: str
    actual: str


class QAReport(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    summary: str
    criteria: list[CriterionResult]
    defects: list[Defect]
