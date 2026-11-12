"""Primary command-line interface (plan §29).

Commands: run · status · claims · report · inspect-claim
"""

from __future__ import annotations

import argparse
import json
import sys

from research_os.storage.database import init_db, session_scope
from research_os.storage.repositories import (
    SqlClaimRepository,
    SqlRunRepository,
    SqlSourceVersionRepository,
    SqlWorkRepository,
)
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim
from research_os.sources.providers import build_providers


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


def _cmd_discover(args: argparse.Namespace) -> int:
    """Run Phase-2 source discovery and print a summary (plan §14).

    ``--fixture DIR`` replays recorded candidates instead of hitting live APIs,
    which keeps demos and regression runs reproducible.
    """
    init_db()
    providers = build_providers(["fixture"], fixture_dir=args.fixture) if args.fixture else None
    with session_scope() as session:
        supervisor = Supervisor(session, providers=providers)
        run = supervisor.create_run(question_text=args.question, domain=args.domain)
        result = supervisor.run_source_discovery(
            run.id, limit=args.limit, max_queries=args.max_queries, fixture_dir=args.fixture
        )
        print(f"run_id:     {result['run_id']}")
        print(f"queries:    {' | '.join(result['queries'])}")
        print(f"candidates: {result['candidates']}")
        print(f"works:      {result['works']}")
        print(f"verified:   {result['verified']}  unverified: {result['unverified']}")
        for error in result["errors"]:
            print(f"provider error: {error}", file=sys.stderr)
        if result["candidates"] == 0:
            print("no candidates discovered; run marked FAILED", file=sys.stderr)
            return 1
    return 0


def _cmd_sources(args: argparse.Namespace) -> int:
    """List discovered works and their versions with verification state."""
    init_db()
    with session_scope() as session:
        run = SqlRunRepository(session).get(args.run_id)
        if run is None:
            print(f"run {args.run_id} not found", file=sys.stderr)
            return 1
        versions = SqlSourceVersionRepository(session).list_by_run(args.run_id)
        if not versions:
            print("no sources discovered for this run", file=sys.stderr)
            return 1

        works = SqlWorkRepository(session)
        grouped: dict[str, list] = {}
        for version in versions:
            grouped.setdefault(version.work_id, []).append(version)

        for work_id, group in grouped.items():
            work = works.get(work_id)
            title = work.canonical_title if work else work_id
            print(f"{title}  ({len(group)} version(s))")
            for version in group:
                marker = "verified" if version.verified else "UNVERIFIED"
                identifier = version.doi or version.arxiv_id or "-"
                tier = version.source_tier.value if version.source_tier else "UNKNOWN"
                venue = f" · {version.venue}" if version.venue else ""
                year = f" · {version.year}" if version.year else ""
                print(f"  [{marker}] {tier} · {identifier}{year}{venue}")
                for note in version.verification_notes:
                    print(f"      note: {note}")
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
    """List the claims of one run with status and confidence.

    Scoped to ``run_id`` on purpose: a global listing would mix one run's
    conclusions into another run's audit trail (plan §28).
    """
    init_db()
    with session_scope() as session:
        claims = SqlClaimRepository(session).list_by_run(args.run_id)
        if not claims:
            print("no claims", file=sys.stderr)
            return 1
        for c in claims:
            scope = c.scope or "undetermined"
            print(f"{c.id}\t[{c.status.value}/{c.confidence_label.value}]\t{scope}\t{c.text}")
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

    p_discover = sub.add_parser("discover", help="run Phase-2 source discovery")
    p_discover.add_argument("--question", required=True)
    p_discover.add_argument("--domain", default=None)
    p_discover.add_argument("--limit", type=int, default=15, help="results per provider per query")
    p_discover.add_argument("--max-queries", type=int, default=2)
    p_discover.add_argument("--fixture", default=None, help="replay local candidate JSON instead of live APIs")
    p_discover.set_defaults(func=_cmd_discover)

    p_sources = sub.add_parser("sources", help="list discovered works and versions")
    p_sources.add_argument("run_id")
    p_sources.set_defaults(func=_cmd_sources)

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
