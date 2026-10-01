"""Command line: `shunya serve` runs the studio; `shunya demo` runs one feature end to end in the terminal."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from shunya.config import load_settings
from shunya.shared.schemas import ApprovalStatus, EventType, TaskStatus


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from shunya.api import create_app

    overrides = {}
    if args.provider:
        overrides["model_provider"] = args.provider
    if "SHUNYA_DEMO_STEP_DELAY" not in os.environ:
        overrides["demo_step_delay"] = 0.9  # scripted steps are instant; pace them so the office can be watched
    settings = load_settings(**overrides)
    print(f"Shunya Studio AI  ->  http://{args.host or settings.host}:{args.port or settings.port}")
    print(f"  model provider : {settings.model_provider}")
    print(f"  unreal engine  : {settings.engine_root or 'not found (builds/tests will be SKIPPED)'}")
    print(f"  game repo      : {settings.game_repo}")
    uvicorn.run(create_app(settings=settings), host=args.host or settings.host, port=args.port or settings.port, log_level="info")
    return 0


async def _demo(args: argparse.Namespace) -> int:
    from shunya.studio import Studio

    overrides = {"model_provider": args.provider} if args.provider else {}
    if args.no_unreal:
        overrides["engine_root"] = None
    studio = await Studio(load_settings(**overrides)).start()
    s = studio.settings
    print(f"provider={s.model_provider}  unreal={'yes' if s.unreal_available else 'no (SKIPPED builds/tests)'}  repo={s.game_repo}\n")

    async def printer() -> None:
        async for e in studio.bus.subscribe():
            p = e.payload
            t = e.timestamp.astimezone().strftime("%H:%M:%S")
            who = (e.agent_id or "").ljust(24)
            match e.type:
                case EventType.AGENT_TOOL_CALLED:
                    print(f"{t} {who} {'ok ' if p['ok'] else 'ERR'} {p['summary']}")
                case EventType.TASK_STATUS_CHANGED:
                    print(f"{t} {'':24} == {e.task_id}: {p['from']} -> {p['to']}  {p.get('reason', '')}")
                case EventType.AGENT_STATUS_CHANGED:
                    if p["to"] in ("MEETING", "BLOCKED", "WAITING_APPROVAL"):
                        print(f"{t} {who} [{p['to']}] {p.get('action', '')}")
                case EventType.MEETING_STARTED | EventType.MEETING_ENDED | EventType.BUG_CREATED | EventType.APPROVAL_REQUIRED | EventType.AGENT_ESCALATED | EventType.BUILD_FAILED | EventType.BUILD_PASSED | EventType.TEST_PASSED | EventType.TEST_FAILED:
                    brief = {k: v for k, v in p.items() if k in ("objective", "title", "risk", "reason", "status", "errors", "passed", "failed", "decisions")}
                    print(f"{t} {who} ** {e.type} {brief}")

    printing = asyncio.create_task(printer())
    await asyncio.sleep(0)
    feature = await studio.orchestrator.submit_feature(args.request)
    code = 0
    try:
        while True:
            await asyncio.sleep(0.3)
            f = studio.store.tasks.get(feature.id)
            pending = studio.store.approvals.list(status=str(ApprovalStatus.PENDING))
            if pending:
                a = pending[0]
                print(f"\n--- APPROVAL REQUIRED {a.id}: {a.requested_action}")
                print(f"    risk {a.risk_level}: {'; '.join(a.risk_reasons)}")
                print(f"    files: {', '.join(a.evidence.get('changed_files', []))}")
                qa = a.evidence.get("qa") or {}
                for c in qa.get("criteria", []):
                    print(f"    [{'x' if c['met'] else ' '}] {c['criterion']}\n          {c['evidence']}")
                if args.approve:
                    answer = "y"
                    print("    --approve given: approving.\n")
                else:
                    answer = (await asyncio.to_thread(input, "    Approve merge into develop? [y/N] ")).strip().lower()
                await studio.approvals.decide(a.id, granted=answer == "y", decided_by="studio_owner", comment="cli demo")
            if f.status in (TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.BLOCKED) and not studio.orchestrator.is_running(feature.id):
                break
        await asyncio.sleep(0.2)
        f = studio.store.tasks.get(feature.id)
        print(f"\nFeature {f.id}: {f.status}")
        for child in [t for t in studio.store.tasks.list(limit=1000) if t.parent_id == f.id]:
            print(f"  {child.id} {child.status}  cost ${child.cost_usd:.4f}  merge {str(child.result.get('merge_commit', '-'))[:10]}")
            if child.result.get("blocked_reason"):
                print(f"    blocked: {child.result['blocked_reason']}")
        if f.result.get("blocked_reason"):
            print(f"  blocked: {f.result['blocked_reason']}")
        code = 0 if f.status == TaskStatus.DONE else 1
    finally:
        printing.cancel()
        await studio.stop()
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shunya", description="Shunya Studio AI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the studio backend and the 2.5D studio UI")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--provider", choices=["scripted", "anthropic"])
    demo = sub.add_parser("demo", help="run one feature request through the whole pipeline in the terminal")
    demo.add_argument("request", nargs="?", default="Create a simple Unreal health component.")
    demo.add_argument("--provider", choices=["scripted", "anthropic"])
    demo.add_argument("--approve", action="store_true", help="auto-approve the final merge (otherwise you are asked)")
    demo.add_argument("--no-unreal", action="store_true", help="skip real compilation/tests even if an engine is installed")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if args.cmd == "serve":
        return _serve(args)
    return asyncio.run(_demo(args))


if __name__ == "__main__":
    sys.exit(main())
