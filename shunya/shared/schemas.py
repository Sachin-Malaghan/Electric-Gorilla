"""Typed domain model shared by every layer (spec sections 5, 9, 10, 11, 14, 24, 28, 36, 39).

Structured payloads are authoritative; human-readable text is presentation only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- agents


class AgentState(StrEnum):
    """Operational state shown by the 2.5D avatar (spec 12)."""

    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    READING = "READING"
    SEARCHING = "SEARCHING"
    CODING = "CODING"
    COMPILING = "COMPILING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    REVIEWING = "REVIEWING"
    MEETING = "MEETING"
    REPORTING = "REPORTING"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"
    OFFLINE = "OFFLINE"


class RunPhase(StrEnum):
    """Agent runtime state machine (spec 6)."""

    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    RETRIEVE_CONTEXT = "RETRIEVE_CONTEXT"
    SELECT_ACTION = "SELECT_ACTION"
    CALL_TOOL = "CALL_TOOL"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"
    REPORT = "REPORT"


class PermissionLevel(StrEnum):
    YES = "YES"
    NO = "NO"
    CONDITIONAL = "CONDITIONAL"  # allowed only inside the agent's own isolated workspace
    APPROVAL = "APPROVAL"  # needs a human approval object


class ModelTier(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    STRONG = "strong"


class ModelConfig(BaseModel):
    tier: ModelTier = ModelTier.STANDARD
    model: str | None = None  # explicit override; otherwise resolved from the tier
    effort: str | None = None  # low | medium | high | xhigh | max
    max_tokens: int = 32000


class EscalationPolicy(BaseModel):
    escalate_to: str | None = None
    after_consecutive_failures: int = 3
    on_budget_exceeded: bool = True


class ValidationPolicy(BaseModel):
    required_checks: list[str] = Field(default_factory=list)  # e.g. ["compile", "tests", "review"]


class Avatar(BaseModel):
    room: str = "engineering"
    color: str = "#4f8cff"
    desk: int = 0


class AgentProfile(BaseModel):
    id: str
    name: str
    department: str
    role: str
    responsibilities: list[str] = Field(default_factory=list)
    model: ModelConfig = Field(default_factory=ModelConfig)
    tools: list[str] = Field(default_factory=list)
    permissions: dict[str, PermissionLevel] = Field(default_factory=dict)
    write_globs: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    max_iterations: int = 30
    max_runtime_s: int = 1800
    max_tool_calls: int = 80
    token_budget: int = 400_000
    cost_budget: float = 5.0
    supervisor: str | None = None
    escalation_policy: EscalationPolicy = Field(default_factory=EscalationPolicy)
    validation_policy: ValidationPolicy = Field(default_factory=ValidationPolicy)
    enabled: bool = False  # disabled definitions exist in the org chart but have no desk occupant (OFFLINE)
    prompts: list[str] = Field(default_factory=list)  # extra role prompt layers, e.g. doc_author, lead_reviewer
    capability: str | None = None  # pipeline capability this agent fills: producer, programmer, reviewer, qa, build ...
    avatar: Avatar = Field(default_factory=Avatar)


class AgentStatus(BaseModel):
    """Live, persisted status of one employee - what the 2.5D office renders."""

    id: str
    state: AgentState = AgentState.IDLE
    task_id: str | None = None
    run_id: str | None = None
    current_action: str = ""
    location: str = "desk"  # desk | meeting:<id> | qa_lab | server_room | whiteboard
    paused: bool = False
    since: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- tasks


class TaskType(StrEnum):
    FEATURE = "FEATURE"
    EPIC = "EPIC"
    DESIGN = "DESIGN"
    IMPLEMENTATION = "IMPLEMENTATION"
    BUG = "BUG"
    REVIEW = "REVIEW"
    QA = "QA"
    DOCUMENTATION = "DOCUMENTATION"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskStatus(StrEnum):
    BACKLOG = "BACKLOG"
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    BUILD = "BUILD"
    QA = "QA"
    FAILED = "FAILED"
    BUG_CREATED = "BUG_CREATED"
    ACCEPTED = "ACCEPTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DONE = "DONE"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


TERMINAL_TASK_STATUSES = {TaskStatus.DONE, TaskStatus.CANCELLED}


class TaskBudget(BaseModel):
    """Per-task limits (spec 32)."""

    max_cost_usd: float = 10.0
    max_llm_calls: int = 120
    max_runtime_s: int = 3600
    max_retries: int = 5


class TaskTransition(BaseModel):
    from_status: TaskStatus | None
    to_status: TaskStatus
    actor: str
    reason: str = ""
    at: datetime = Field(default_factory=utcnow)


class Task(BaseModel):
    id: str
    type: TaskType
    title: str
    description: str = ""
    owner: str | None = None
    created_by: str = "user"
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.BACKLOG
    parent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assignee_capability: str = "programmer"
    review_capability: str = "reviewer"
    track: str = "code"  # code | doc | content - which pipeline variant handles this task
    test_filter: str = ""  # Unreal automation test path prefix that verifies this task
    branch: str | None = None
    worktree: str | None = None
    paused: bool = False
    attempts: dict[str, int] = Field(default_factory=dict)  # build / review / qa round counters
    budget: TaskBudget = Field(default_factory=TaskBudget)
    cost_usd: float = 0.0
    llm_calls: int = 0
    tokens: int = 0
    trace_id: str = Field(default_factory=lambda: new_id("TRACE"))
    feedback: list[str] = Field(default_factory=list)  # review / build / QA findings handed back to the owner
    result: dict[str, Any] = Field(default_factory=dict)
    history: list[TaskTransition] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- runs / tools / cost


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    INTERRUPTED = "INTERRUPTED"


class AgentRun(BaseModel):
    id: str = Field(default_factory=lambda: new_id("RUN"))
    agent_id: str
    task_id: str | None = None
    trace_id: str | None = None
    purpose: str = ""
    status: RunStatus = RunStatus.RUNNING
    phase: RunPhase = RunPhase.IDLE
    model: str = ""
    iterations: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    files_inspected: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    report: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


class ToolCallRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("TC"))
    run_id: str
    agent_id: str
    task_id: str | None = None
    trace_id: str | None = None
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    summary: str = ""
    error: str | None = None
    latency_ms: int = 0
    timestamp: datetime = Field(default_factory=utcnow)


class CostRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("COST"))
    run_id: str
    task_id: str | None = None
    agent_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- events


class EventType(StrEnum):
    AGENT_CREATED = "AGENT_CREATED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_STATUS_CHANGED = "AGENT_STATUS_CHANGED"
    AGENT_TOOL_CALLED = "AGENT_TOOL_CALLED"
    AGENT_WAITING = "AGENT_WAITING"
    AGENT_FAILED = "AGENT_FAILED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_ESCALATED = "AGENT_ESCALATED"

    TASK_CREATED = "TASK_CREATED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_STARTED = "TASK_STARTED"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"

    BUILD_STARTED = "BUILD_STARTED"
    BUILD_FAILED = "BUILD_FAILED"
    BUILD_PASSED = "BUILD_PASSED"

    TEST_STARTED = "TEST_STARTED"
    TEST_FAILED = "TEST_FAILED"
    TEST_PASSED = "TEST_PASSED"

    BUG_CREATED = "BUG_CREATED"
    MESSAGE_SENT = "MESSAGE_SENT"

    MEETING_STARTED = "MEETING_STARTED"
    MEETING_ENDED = "MEETING_ENDED"

    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"

    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    COST_RECORDED = "COST_RECORDED"
    STUDIO_RECOVERED = "STUDIO_RECOVERED"


class Event(BaseModel):
    id: str = Field(default_factory=lambda: new_id("EVT"))
    seq: int = 0  # assigned by the event log, monotonically increasing
    type: EventType
    timestamp: datetime = Field(default_factory=utcnow)
    trace_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- communication


class MessageType(StrEnum):
    TASK_HANDOFF = "TASK_HANDOFF"
    REVIEW_FEEDBACK = "REVIEW_FEEDBACK"
    BUILD_FAILURE = "BUILD_FAILURE"
    BUG_REPORT = "BUG_REPORT"
    STATUS_REPORT = "STATUS_REPORT"
    ESCALATION = "ESCALATION"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AgentMessage(BaseModel):
    """Structured agent-to-agent communication (spec 10)."""

    id: str = Field(default_factory=lambda: new_id("MSG"))
    type: MessageType
    sender: str
    receiver: str
    task_id: str | None = None
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.MEDIUM
    timestamp: datetime = Field(default_factory=utcnow)


class CollaborationSession(BaseModel):
    """A meeting (spec 14). The collaboration itself happens in the backend."""

    id: str = Field(default_factory=lambda: new_id("MEET"))
    objective: str
    participants: list[str]
    room: str = "meeting_room_1"
    task_id: str | None = None
    shared_context: str = ""
    decisions: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    status: str = "OPEN"
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


# --------------------------------------------------------------------------- artifacts / build / test / bugs / approvals


class ArtifactType(StrEnum):
    GAME_DESIGN_DOCUMENT = "GameDesignDocument"
    TECHNICAL_DESIGN = "TechnicalDesign"
    FEATURE_PLAN = "FeaturePlan"
    IMPLEMENTATION_PLAN = "ImplementationPlan"
    CODE_PATCH = "CodePatch"
    TEST_PLAN = "TestPlan"
    TEST_REPORT = "TestReport"
    BUG_REPORT = "BugReport"
    REVIEW_REPORT = "ReviewReport"
    PERFORMANCE_REPORT = "PerformanceReport"
    BUILD_LOG = "BuildLog"
    BUILD_ARTIFACT = "BuildArtifact"
    GENERATED_ASSET = "GeneratedAsset"
    ARCHITECTURE_DECISION = "ArchitectureDecision"
    MEETING_NOTES = "MeetingNotes"


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ART"))
    type: ArtifactType
    title: str
    creator: str
    task_id: str | None = None
    version: int = 1
    status: str = "DRAFT"
    storage_location: str = ""
    content_type: str = "text/plain"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class CompileDiagnostic(BaseModel):
    file: str = ""
    line: int | None = None
    column: int | None = None
    severity: str = "error"
    code: str = ""
    message: str

    def fingerprint(self) -> str:
        return f"{self.code}:{self.file.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{self.message[:80]}"


class BuildStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # no engine configured - never reported as a pass
    ERROR = "ERROR"  # the build tool itself failed (timeout, missing files)


class BuildRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("B"))
    task_id: str | None = None
    agent_id: str = "build_engineer_01"
    target: str = ""
    status: BuildStatus
    duration_s: float = 0.0
    diagnostics: list[CompileDiagnostic] = Field(default_factory=list)
    log_artifact_id: str | None = None
    log_tail: str = ""
    commit: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TestCaseResult(BaseModel):
    name: str
    result: str  # PASS | FAIL | SKIPPED
    duration_s: float = 0.0
    messages: list[str] = Field(default_factory=list)


class TestRunRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("T"))
    task_id: str | None = None
    build_id: str | None = None
    commit: str | None = None
    filter: str = ""
    status: str  # PASSED | FAILED | SKIPPED | ERROR
    passed: int = 0
    failed: int = 0
    results: list[TestCaseResult] = Field(default_factory=list)
    log_artifact_id: str | None = None
    duration_s: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class Bug(BaseModel):
    id: str = Field(default_factory=lambda: new_id("BUG"))
    task_id: str
    title: str
    severity: Severity = Severity.HIGH
    reporter: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: str = "OPEN"
    created_at: datetime = Field(default_factory=utcnow)


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"


class Approval(BaseModel):
    """Human approval gate (spec 28)."""

    id: str = Field(default_factory=lambda: new_id("APR"))
    task_id: str
    agent_id: str
    requested_action: str
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_reasons: list[str] = Field(default_factory=list)
    diff_artifact_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    comment: str = ""
    rework_requested: bool = False  # on rejection: send back to engineering instead of cancelling
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- memory / knowledge


class MemoryKind(StrEnum):
    PROJECT = "project"  # architecture, GDD, standards, decisions
    EPISODIC = "episodic"  # previous task history
    OPERATIONAL = "operational"  # builds, tests, failures


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("MEM"))
    kind: MemoryKind
    agent_id: str | None = None
    task_id: str | None = None
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class KnowledgeChunk(BaseModel):
    id: str
    source: str
    kind: str  # doc | code | adr
    start_line: int = 1
    content: str
    vector: list[float] = Field(default_factory=list)


class Project(BaseModel):
    id: str = "shunya"
    name: str = "Shunya"
    repo_path: str = ""
    engine_root: str | None = None
    description: str = ""
