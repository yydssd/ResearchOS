"""Primary command-line interface (plan §29).

Commands: run · status · claims · report · inspect-claim
"""

from __future__ import annotations

import argparse
import json
import sys

from research_os.storage.database import init_db, session_scope
from research_os.storage.repositories import SqlClaimRepository, SqlRunRepository
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the Week-1 vertical slice on local sources (or create a run only)."""
    init_db()
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=args.question, domain=args.domain)
        sources = [(p, None, "auto") for p in args.source]
        if sources:
            result = supervisor.run_vertical_slice(run_id=run.id, sources=sources)
            print(f"run_id: {result['run_id']}")
            print(f"status: {result['status']}")
            print(f"report: {result['report_path']}")
        else:
            print(f"run_id: {run.id} (created; pass --source to run the vertical slice)")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show run status, phase, and any warnings."""
    init_db()
    with session_scope() as session:
        run = SqlRunRepository(session).get(args.run_id)
        if run is None:
            print(f"run {args.run_id} not found", file=sys.stderr)
            return 1
        print(f"run_id: {run.id}")
        print(f"status: {run.status.value}")
        print(f"phase:  {run.current_phase}")
        for w in run.warnings:
            print(f"warning: {w}")
    return 0


def _cmd_claims(args: argparse.Namespace) -> int:
    """List claims with status and confidence."""
    init_db()
    with session_scope() as session:
        claims = SqlClaimRepository(session).list_all()
        if not claims:
            print("no claims", file=sys.stderr)
            return 1
        for c in claims:
            print(f"{c.id}\t[{c.status.value}/{c.confidence_label.value}]\t{c.text}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Print the Markdown research memo for a run."""
    init_db()
    with session_scope() as session:
        memo = build_memo_from_run(session, args.run_id)
        if memo is None:
            print(f"run {args.run_id} not found", file=sys.stderr)
            return 1
        print(memo)
    return 0


def _cmd_inspect_claim(args: argparse.Namespace) -> int:
    """Print the trace chain claim -> evidence -> source version -> location."""
    init_db()
    with session_scope() as session:
        info = inspect_claim(session, args.run_id, args.claim_id)
        if info is None:
            print("claim not found in this run", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-os", description="ResearchOS research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the Week-1 vertical slice on local sources")
    p_run.add_argument("--question", required=True)
    p_run.add_argument("--domain", default=None)
    p_run.add_argument("--source", action="append", default=[], help="local source path (repeatable)")
    p_run.set_defaults(func=_cmd_run)

    p_status = sub.add_parser("status", help="show run status")
    p_status.add_argument("run_id")
    p_status.set_defaults(func=_cmd_status)

    p_claims = sub.add_parser("claims", help="list claims")
    p_claims.add_argument("run_id")
    p_claims.set_defaults(func=_cmd_claims)

    p_report = sub.add_parser("report", help="print the Markdown research memo")
    p_report.add_argument("run_id")
    p_report.set_defaults(func=_cmd_report)

    p_inspect = sub.add_parser("inspect-claim", help="show the trace chain for one claim")
    p_inspect.add_argument("run_id")
    p_inspect.add_argument("claim_id")
    p_inspect.set_defaults(func=_cmd_inspect_claim)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
