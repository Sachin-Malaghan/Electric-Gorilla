"""Human approval gates (spec 28) and deterministic risk scoring."""

from __future__ import annotations

import asyncio
import fnmatch

from shunya.core.interfaces import IApprovalService, IEventBus
from shunya.core.permissions import DEFAULT_PROTECTED_GLOBS
from shunya.core.persistence import Store
from shunya.shared.schemas import Approval, ApprovalStatus, Event, EventType, RiskLevel, utcnow


def assess_risk(*, changed_files: list[str], diff: str, build_status: str, tests_status: str) -> tuple[RiskLevel, list[str]]:
    """Risk is computed by code from facts, not asserted by an agent."""
    reasons: list[str] = []
    level = RiskLevel.LOW
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

    def bump(to: RiskLevel, why: str) -> None:
        nonlocal level
        reasons.append(why)
        if order.index(to) > order.index(level):
            level = to

    # recipes and generated source files describe the same assets as the .uasset files next to them
    counted = [f for f in changed_files if not f.startswith(("ContentJobs/", "SourceArt/"))]
    protected = [f for f in changed_files if any(fnmatch.fnmatch(f, g) for g in DEFAULT_PROTECTED_GLOBS)]
    if protected:
        bump(RiskLevel.HIGH, f"project configuration / dependency files changed: {', '.join(protected[:5])}")
    deleted = diff.count("\ndeleted file mode")
    if deleted:
        bump(RiskLevel.HIGH, f"{deleted} file(s) deleted")
    changed_lines = sum(1 for l in diff.splitlines() if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
    if len(counted) > 15 or changed_lines > 1500:
        bump(RiskLevel.HIGH, f"large change: {len(counted)} files, {changed_lines} lines")
    elif len(counted) > 8 or changed_lines > 600:
        bump(RiskLevel.MEDIUM, f"medium-sized change: {len(counted)} files, {changed_lines} lines")
    if build_status not in ("PASSED", "NOT_APPLICABLE"):
        bump(RiskLevel.HIGH, f"build not verified (status: {build_status})")
    if tests_status not in ("PASSED", "NOT_APPLICABLE"):
        bump(RiskLevel.HIGH, f"automated tests not verified (status: {tests_status})")
    if not reasons:
        reasons.append("small, compiled, tested change confined to agent-writable source folders")
    return level, reasons


class ApprovalService(IApprovalService):
    def __init__(self, store: Store, bus: IEventBus):
        self.store = store
        self.bus = bus
        self._waiters: dict[str, asyncio.Event] = {}

    async def request(self, approval: Approval) -> Approval:
        self.store.approvals.put(approval)
        await self.bus.publish(
            Event(
                type=EventType.APPROVAL_REQUIRED, task_id=approval.task_id, agent_id=approval.agent_id,
                payload={"approval_id": approval.id, "action": approval.requested_action, "risk": approval.risk_level, "reason": approval.reason},
            )
        )
        return approval

    async def decide(self, approval_id: str, *, granted: bool, decided_by: str, comment: str = "", rework: bool = False) -> Approval:
        approval = self.store.approvals.get(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"approval {approval_id} is already {approval.status}")
        approval.status = ApprovalStatus.GRANTED if granted else ApprovalStatus.REJECTED
        approval.decided_by, approval.decided_at, approval.comment = decided_by, utcnow(), comment
        approval.rework_requested = bool(rework and not granted)
        self.store.approvals.put(approval)
        await self.bus.publish(
            Event(
                type=EventType.APPROVAL_GRANTED if granted else EventType.APPROVAL_REJECTED,
                task_id=approval.task_id, agent_id=decided_by,
                payload={"approval_id": approval.id, "comment": comment, "rework": approval.rework_requested},
            )
        )
        if approval_id in self._waiters:
            self._waiters[approval_id].set()
        return approval

    async def wait(self, approval_id: str) -> Approval:
        """Block until a human decides. Survives restarts: state is re-read from the store."""
        event = self._waiters.setdefault(approval_id, asyncio.Event())
        while True:
            approval = self.store.approvals.get(approval_id)
            if approval is None:
                raise KeyError(approval_id)
            if approval.status != ApprovalStatus.PENDING:
                self._waiters.pop(approval_id, None)
                return approval
            try:
                await asyncio.wait_for(event.wait(), timeout=2.0)
            except TimeoutError:
                pass

    def pending(self) -> list[Approval]:
        return self.store.approvals.list(status=str(ApprovalStatus.PENDING), newest_first=True)
