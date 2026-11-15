"""Supervisor: run state machine, budget ownership, Week-1 vertical slice.

The supervisor owns budget enforcement (plan §26); individual components may
not override global limits. Failures are surfaced and persisted as events
(plan §25) — never silently swallowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from research_os.config import settings
from research_os.documents.chunks import chunk_pages
from research_os.documents.loader import DocumentLoadError, load_document, make_source_version
from research_os.domain.enums import (
    EventType,
    EvidenceRelation,
    FailureType,
    RunStatus,
    TaskStatus,
    TaskType,
)
from research_os.domain.models import (
    ResearchBudget,
    ResearchEvent,
    ResearchQuestion,
    ResearchRun,
    ResearchWork,
    new_id,
)
from research_os.orchestration.tasks import complete_task, create_task
from research_os.reporting.memo import build_memo_from_run
from research_os.research.claim_builder import ClaimBuilder, HeuristicClaimBuilder
from research_os.research.contradiction import ContradictionAssessor, HeuristicContradictionAssessor
from research_os.research.evidence_extractor import (
    EvidenceExtractor,
    HeuristicEvidenceExtractor,
    has_location,
)
from research_os.research.methods import MethodExtractor, extract_methods
from research_os.research.quantitative import HeuristicQuantitativeExtractor, QuantitativeExtractor
from research_os.sources.discovery import collect_candidates, dedupe_candidates
from research_os.sources.providers import ProviderError, SearchProvider, build_providers
from research_os.sources.query import build_queries
from research_os.sources.resolver import resolve_candidates
from research_os.storage.repositories import (
    CrossRunPairError,
    SqlChunkRepository,
    SqlClaimEvidenceRelationRepository,
    SqlClaimRepository,
    SqlContradictionRepository,
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlMethodProfileRepository,
    SqlQuestionRepository,
    SqlQuantitativeEvidenceRepository,
    SqlRunRepository,
    SqlSourceCandidateRepository,
    SqlSourceVersionRepository,
    SqlWorkRepository,
)

DEFAULT_REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reports"


def _unlocatable_claims(assessments, relations) -> list[str]:
    """Assessed claims with no SUPPORTS relation.

    Same definition the memo uses: without supporting evidence a claim renders as
    "no locatable evidence", so the event and the prose cannot disagree.
    """
    involved = {cid for item in assessments for cid in (item.claim_a_id, item.claim_b_id)}
    # `==` rather than `is`: the enum is a StrEnum, and an upstream row that
    # carries the bare string "SUPPORTS" must not be silently treated as
    # unsupported. The memo compares the same way.
    supported = {
        relation.claim_id
        for relation in relations
        if relation.relation == EvidenceRelation.SUPPORTS
    }
    return sorted(cid for cid in involved if cid not in supported)


class Supervisor:
    def __init__(
        self,
        session: Session,
        evidence_extractor: EvidenceExtractor | None = None,
        claim_builder: ClaimBuilder | None = None,
        providers: list[SearchProvider] | None = None,
        quantitative_extractor: QuantitativeExtractor | None = None,
        contradiction_assessor: ContradictionAssessor | None = None,
        method_extractor: MethodExtractor | None = None,
    ) -> None:
        self._session = session
        self._extractor = evidence_extractor or HeuristicEvidenceExtractor()
        self._builder = claim_builder or HeuristicClaimBuilder()
        self._quantitative = quantitative_extractor or HeuristicQuantitativeExtractor()
        self._assessor = contradiction_assessor or HeuristicContradictionAssessor()
        # Method acquisition is deterministic (design §6); the L3 describer that
        # is not deterministic arrives in S3 as a separate, optional component.
        self._methods = method_extractor
        # Injected for tests/offline runs; otherwise resolved from settings at
        # call time so configuration changes are picked up without re-import.
        self._providers = providers

    # -- state & events -----------------------------------------------------

    def _log(
        self,
        run_id: str,
        event_type: EventType,
        message: str = "",
        payload: dict[str, Any] | None = None,
        failure_type: FailureType | None = None,
    ) -> None:
        SqlEventRepository(self._session).create(
            ResearchEvent(run_id=run_id, event_type=event_type, message=message, payload=payload or {}, failure_type=failure_type)
        )

    def _transition(self, run: ResearchRun, status: RunStatus, phase: str) -> None:
        run.status = status
        run.current_phase = phase
        SqlRunRepository(self._session).update(run)
        self._log(run.id, EventType.RUN_STATE_CHANGED, f"run -> {status.value}", {"phase": phase})

    def _budget(self, run: ResearchRun) -> ResearchBudget:
        return run.budget

    def _check_budget(self, run: ResearchRun) -> None:
        if self._budget(run).exceeded():
            self._log(run.id, EventType.BUDGET_EXCEEDED, "global budget exceeded", failure_type=FailureType.BUDGET_EXCEEDED)
            run.warnings.append("global budget exceeded")
            SqlRunRepository(self._session).update(run)

    # -- public API ---------------------------------------------------------

    def create_run(self, question_text: str, domain: str | None = None) -> ResearchRun:
        question = ResearchQuestion(question=question_text, domain=domain)
        SqlQuestionRepository(self._session).create(question)
        run = ResearchRun(
            question_id=question.id,
            status=RunStatus.CREATED,
            current_phase="created",
            budget=ResearchBudget(
                max_llm_calls=settings.max_llm_calls,
                max_search_calls=settings.max_search_calls,
                max_sources_discovered=settings.max_sources_discovered,
                max_sources_deep_read=settings.max_sources_deep_read,
                max_cost_usd=settings.max_cost_usd,
            ),
        )
        SqlRunRepository(self._session).create(run)
        self._log(run.id, EventType.RUN_CREATED, "run created", {"question": question_text})
        return run

    def get_run(self, run_id: str) -> ResearchRun | None:
        """Fetch lightweight run state (status, phase, warnings, budget)."""
        return SqlRunRepository(self._session).get(run_id)

    def run_source_discovery(
        self,
        run_id: str,
        limit: int = 15,
        max_queries: int = 2,
        fixture_dir: str | None = None,
    ) -> dict[str, Any]:
        """Phase 2 (plan §14): question -> queries -> providers -> candidates
        -> canonical works + verified versions.

        The supervisor owns budget accounting (plan §26): every provider call is
        counted here, and a provider failure is persisted as a typed event
        instead of aborting the run.
        """
        run = SqlRunRepository(self._session).get(run_id)
        if run is None:
            raise KeyError(f"run {run_id} not found")
        question = SqlQuestionRepository(self._session).get(run.question_id)
        if question is None:
            raise KeyError(f"question {run.question_id} not found")

        providers = self._providers or build_providers(settings.provider_names, fixture_dir=fixture_dir)
        self._transition(run, RunStatus.RESEARCHING, "discover")
        task = create_task(self._session, run.id, TaskType.DISCOVER_SOURCES, status=TaskStatus.RUNNING)
        queries = build_queries(question.question, max_queries=max_queries)

        def before_search(provider_name: str, query: str) -> bool:
            """Count the call and stop the loop once the global budget is spent."""
            if run.budget.exceeded():
                self._log(
                    run.id,
                    EventType.BUDGET_EXCEEDED,
                    "search budget exhausted; discovery stopped",
                    {"provider": provider_name},
                    failure_type=FailureType.BUDGET_EXCEEDED,
                )
                return False
            run.budget.search_calls += 1
            SqlRunRepository(self._session).update(run)
            return True

        def on_error(provider_name: str, exc: ProviderError) -> None:
            self._log(
                run.id,
                EventType.FAILURE,
                f"{provider_name} search failed: {exc}",
                {"provider": provider_name},
                failure_type=exc.failure_type,
            )

        outcome = collect_candidates(
            providers, queries, limit, before_search=before_search, on_error=on_error
        )
        # Running several queries through the same provider returns the same
        # record more than once; dedupe before it inflates budget/coverage counts.
        candidates = dedupe_candidates(outcome.candidates)

        candidate_repo = SqlSourceCandidateRepository(self._session)
        candidate_repo.create_many(candidates, run_id=run.id)

        resolutions = resolve_candidates(candidates)
        work_repo = SqlWorkRepository(self._session)
        version_repo = SqlSourceVersionRepository(self._session)
        verified = 0
        unverified = 0

        for resolution in resolutions:
            work_repo.create(resolution.work)
            for version in resolution.versions:
                version_repo.create(version, run_id=run.id)
            for candidate_id, version_id in resolution.candidate_to_version.items():
                candidate_repo.attach_resolution(candidate_id, resolution.work.id, version_id)

            for version in resolution.versions:
                if version.verified:
                    verified += 1
                    self._log(
                        run.id,
                        EventType.SOURCE_VERIFIED,
                        f"verified: {version.title}",
                        {
                            "source_version_id": version.id,
                            "work_id": resolution.work.id,
                            "tier": version.source_tier.value if version.source_tier else None,
                            "notes": version.verification_notes,
                        },
                    )
                else:
                    unverified += 1
                    self._log(
                        run.id,
                        EventType.FAILURE,
                        f"unverified source: {version.title}: {'; '.join(version.verification_notes)}",
                        {"source_version_id": version.id, "work_id": resolution.work.id},
                        failure_type=(
                            FailureType.SOURCE_IDENTITY_AMBIGUOUS
                            if resolution.ambiguous
                            else FailureType.SOURCE_UNAVAILABLE
                        ),
                    )

        run.budget.sources_discovered += len(candidates)
        SqlRunRepository(self._session).update(run)
        self._log(
            run.id,
            EventType.SOURCE_DISCOVERED,
            f"{len(candidates)} candidates -> {len(resolutions)} works",
            {
                "candidates": len(candidates),
                "works": len(resolutions),
                "verified": verified,
                "unverified": unverified,
                "queries": queries,
                "errors": outcome.errors,
            },
        )

        if not candidates:
            complete_task(self._session, task, output_ids=[])
            self._transition(run, RunStatus.FAILED, "no candidates discovered")
            self._log(
                run.id,
                EventType.TASK_FAILED,
                "no source candidates discovered",
                failure_type=FailureType.SEARCH_STAGNATION,
            )
        else:
            complete_task(
                self._session,
                task,
                output_ids=[v.id for r in resolutions for v in r.versions],
            )
            run.current_phase = "sources-ready"
            SqlRunRepository(self._session).update(run)

        return {
            "run_id": run.id,
            "queries": queries,
            "candidates": len(candidates),
            "works": len(resolutions),
            "verified": verified,
            "unverified": unverified,
            "resolutions": resolutions,
            "errors": outcome.errors,
        }

    def run_vertical_slice(
        self,
        run_id: str,
        sources: list[tuple[str, str | None, str]],
        reports_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Week-1 vertical slice (plan §13): local sources -> evidence ->
        claims -> relations -> Markdown memo. No live search."""
        run = SqlRunRepository(self._session).get(run_id)
        if run is None:
            raise KeyError(f"run {run_id} not found")
        question = SqlQuestionRepository(self._session).get(run.question_id)
        assert question is not None

        self._transition(run, RunStatus.RESEARCHING, "load+extract")
        self._check_budget(run)

        # 1) register works + source versions, load documents
        all_chunks: list[Any] = []
        registered: list[tuple] = []
        for path, title, declared_type in sources:
            try:
                pages = load_document(path, declared_type)
            except DocumentLoadError as exc:
                self._log(run.id, EventType.FAILURE, str(exc), {"path": path}, failure_type=exc.failure_type)
                run.warnings.append(f"load failed: {path}: {exc}")
                SqlRunRepository(self._session).update(run)
                continue

            work = ResearchWork(canonical_title=title or Path(path).stem, authors=[])
            SqlWorkRepository(self._session).create(work)
            sv = make_source_version(work.id, path, title or "", verified=True)
            SqlSourceVersionRepository(self._session).create(sv, run_id=run.id)
            registered.append((work, sv))
            all_chunks.extend(chunk_pages(pages, sv.id))

        if not all_chunks:
            self._transition(run, RunStatus.FAILED, "no loadable sources")
            self._log(run.id, EventType.TASK_FAILED, "no sources could be loaded", failure_type=FailureType.SOURCE_UNAVAILABLE)
            return {"run_id": run.id, "status": run.status.value, "memo": ""}

        # Chunks are persisted before extraction so every Evidence.chunk_id stays
        # resolvable after the run (plan §15: provenance must survive the process).
        SqlChunkRepository(self._session).create_many(all_chunks)

        # 2) evidence extraction, gated on locatability (plan §2.2)
        extract_task = create_task(self._session, run.id, TaskType.EXTRACT_EVIDENCE, status=TaskStatus.RUNNING)
        raw_evidence = self._extractor.extract(all_chunks)
        evidence = [ev for ev in raw_evidence if has_location(ev)]
        rejected = len(raw_evidence) - len(evidence)
        if rejected:
            self._log(
                run.id,
                EventType.FAILURE,
                f"{rejected} evidence object(s) rejected: no source location",
                {"rejected": rejected},
                failure_type=FailureType.CITATION_LOCATION_MISSING,
            )
            run.warnings.append(f"CITATION_LOCATION_MISSING: {rejected} evidence object(s) lacked a location")
            SqlRunRepository(self._session).update(run)

        ev_repo = SqlEvidenceRepository(self._session)
        for ev in evidence:
            ev_repo.create(ev)
        complete_task(self._session, extract_task, output_ids=[ev.id for ev in evidence])

        # 3) method acquisition (design §6): name, components, setup per source.
        # Runs before the quantitative pass because that pass fills
        # `QuantitativeEvidence.method` with the resolved name (design §10.3).
        method_task = create_task(self._session, run.id, TaskType.EXTRACT_METHOD, status=TaskStatus.RUNNING)
        extraction = (
            self._methods.extract(all_chunks, domain=question.domain)
            if self._methods is not None
            else extract_methods(all_chunks, domain=question.domain)
        )
        SqlMethodProfileRepository(self._session).upsert_many(extraction.profiles, run.id)
        for source_version_id, candidates in extraction.ambiguous.items():
            # Logged, not swallowed: "no name because the paper never chooses one"
            # and "no name because nothing matched" are different defects.
            self._log(
                run.id,
                EventType.METHOD_NAME_AMBIGUOUS,
                f"ambiguous method name: {', '.join(candidates)}",
                {"source_version_id": source_version_id, "candidates": list(candidates)},
            )
        for profile in extraction.profiles:
            if profile.aliases:
                self._log(
                    run.id,
                    EventType.METHOD_MULTI_NAME,
                    f"{len(profile.aliases) + 1} method names in one paper",
                    {
                        "source_version_id": profile.source_version_id,
                        "name": profile.name,
                        "aliases": list(profile.aliases),
                    },
                )
        complete_task(
            self._session,
            method_task,
            output_ids=[profile.source_version_id for profile in extraction.profiles],
        )

        # 4) quantitative evidence (plan §15): structured numbers, separate table
        facts = self._quantitative.extract(evidence)
        SqlQuantitativeEvidenceRepository(self._session).create_many(facts)
        self._log(
            run.id,
            EventType.EVIDENCE_EXTRACTED,
            f"{len(evidence)} evidence objects, {len(facts)} quantitative facts",
            {"count": len(evidence), "quantitative": len(facts), "rejected": rejected},
        )

        # 4) claim construction + relations. Chunks and quantitative facts are
        # passed in because identity needs block context (task from the section
        # heading) and reported values (P4 spec §4/§6).
        build_task = create_task(self._session, run.id, TaskType.BUILD_CLAIM)
        claims, relations = self._builder.build(evidence, quantitative=facts, chunks=all_chunks)
        claim_repo = SqlClaimRepository(self._session)
        rel_repo = SqlClaimEvidenceRelationRepository(self._session)
        for claim in claims:
            claim_repo.create(claim, run_id=run.id)
        for rel in relations:
            rel_repo.create(rel)
        complete_task(self._session, build_task, output_ids=[c.id for c in claims])
        self._log(run.id, EventType.CLAIM_BUILT, f"{len(claims)} claims, {len(relations)} relations",
                  {"claims": len(claims), "relations": len(relations)})

        # 4b) pairwise contradiction assessment (plan §17). Claims are read-only
        # here on purpose: P4 owns status and confidence, P5 only relates them.
        assess_task = create_task(self._session, run.id, TaskType.CHECK_CONTRADICTION)
        assessments, stats = self._assessor.assess(claims)
        # Computed before the write because the cross-run branch below empties
        # `assessments`; the run that most needs "evidence is not locatable" is
        # exactly the one whose batch was rejected.
        unlocatable = _unlocatable_claims(assessments, relations)
        dropped = 0
        try:
            replaced = SqlContradictionRepository(self._session).replace_for_run(run.id, assessments)
        except CrossRunPairError as exc:
            # Plan §25 asks for a persisted failure event, not for the run to die.
            # Only the dedicated type is caught: a pydantic ValidationError is also
            # a ValueError, and relabelling one as a cross-run rejection would drop
            # the batch silently instead of surfacing a real schema defect.
            dropped = len(assessments)
            self._log(
                run.id,
                EventType.FAILURE,
                str(exc),
                {
                    "dropped": dropped,
                    "claim_a_id": exc.claim_a_id,
                    "claim_b_id": exc.claim_b_id,
                },
                failure_type=FailureType.CROSS_RUN_PAIR,
            )
            assessments, replaced = [], 0
            run.warnings.append(f"CROSS_RUN_PAIR: {dropped} assessment(s) not written")
            SqlRunRepository(self._session).update(run)
        complete_task(self._session, assess_task, output_ids=[a.claim_a_id for a in assessments])
        if stats.failed_pairs:
            self._log(
                run.id,
                EventType.FAILURE,
                f"contradiction assessor raised on {stats.failed_pairs} of {stats.evaluated} pairs",
                {
                    "failed_pairs": stats.failed_pairs,
                    "evaluated": stats.evaluated,
                    "total_before_cap": stats.total_before_cap,
                    "by_error": stats.failed_by_error,
                    "first_failure": stats.first_failure,
                },
                failure_type=FailureType.CONTRADICTION_UNRESOLVED,
            )
            run.warnings.append(
                f"CONTRADICTION_UNRESOLVED: {stats.failed_pairs} pair(s) failed to judge"
            )
            SqlRunRepository(self._session).update(run)

        if stats.skipped_same_value:
            # A same-value pair means P4's merge gate let a duplicate through.
            # The counter alone answers "how many" but never says which run needs
            # its dedup looked at, so the defect also lands in the failure record.
            self._log(
                run.id,
                EventType.FAILURE,
                f"{stats.skipped_same_value} pair(s) share an identical value",
                {"skipped_same_value": stats.skipped_same_value},
                failure_type=FailureType.CONTRADICTION_UNRESOLVED,
            )
            run.warnings.append(
                f"CONTRADICTION_UNRESOLVED: {stats.skipped_same_value} pair(s) share an identical value"
            )
            SqlRunRepository(self._session).update(run)

        if unlocatable:
            # The memo already prints "no locatable evidence" next to such a claim,
            # but prose is not queryable; the event makes the same gap filterable
            # across runs without reading every memo.
            self._log(
                run.id,
                EventType.FAILURE,
                f"{len(unlocatable)} assessed claims have no locatable evidence",
                {"claim_ids": unlocatable},
                failure_type=FailureType.CITATION_LOCATION_MISSING,
            )
            run.warnings.append(
                f"CITATION_LOCATION_MISSING: {len(unlocatable)} assessed claim(s) have no locatable evidence"
            )
            SqlRunRepository(self._session).update(run)
        self._log(
            run.id,
            EventType.CONTRADICTION_ASSESSED,
            f"{len(assessments)} assessments written from {stats.evaluated} pairs"
            + (f" ({dropped} dropped)" if dropped else "")
            + (f" ({stats.failed_pairs} failed)" if stats.failed_pairs else ""),
            {
                "assessments": len(assessments),
                "total_before_cap": stats.total_before_cap,
                "evaluated": stats.evaluated,
                "judged": stats.judged,
                "failed_pairs": stats.failed_pairs,
                "coverage": round(stats.coverage, 4),
                "skipped_missing_dataset": stats.skipped_missing_dataset,
                "skipped_missing_metric": stats.skipped_missing_metric,
                "skipped_self_prefilter": stats.skipped_self_prefilter,
                "skipped_same_value": stats.skipped_same_value,
                "skipped_cap": stats.skipped_cap,
                "by_type": stats.emitted_by_type,
                "replaced": replaced,
                "dropped": dropped,
            },
        )

        # 5) memo
        self._transition(run, RunStatus.SYNTHESIZING, "memo")
        memo = build_memo_from_run(self._session, run.id) or ""
        out_dir = reports_dir or DEFAULT_REPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"{run.id}.md"
        report_path.write_text(memo, encoding="utf-8")

        self._transition(run, RunStatus.COMPLETED, "completed")
        self._log(run.id, EventType.RUN_STATE_CHANGED, "vertical slice completed", {"report": str(report_path)})
        return {"run_id": run.id, "status": run.status.value, "memo": memo, "report_path": str(report_path)}
