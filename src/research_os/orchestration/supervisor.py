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
from research_os.domain.enums import EventType, FailureType, RunStatus, TaskStatus, TaskType
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
from research_os.research.evidence_extractor import EvidenceExtractor, HeuristicEvidenceExtractor
from research_os.storage.repositories import (
    SqlClaimEvidenceRelationRepository,
    SqlClaimRepository,
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlQuestionRepository,
    SqlRunRepository,
    SqlSourceVersionRepository,
    SqlWorkRepository,
)

DEFAULT_REPORTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reports"


class Supervisor:
    def __init__(
        self,
        session: Session,
        evidence_extractor: EvidenceExtractor | None = None,
        claim_builder: ClaimBuilder | None = None,
    ) -> None:
        self._session = session
        self._extractor = evidence_extractor or HeuristicEvidenceExtractor()
        self._builder = claim_builder or HeuristicClaimBuilder()

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

        # 2) evidence extraction
        extract_task = create_task(self._session, run.id, TaskType.EXTRACT_EVIDENCE, status=TaskStatus.RUNNING)
        evidence = self._extractor.extract(all_chunks)
        ev_repo = SqlEvidenceRepository(self._session)
        for ev in evidence:
            ev_repo.create(ev)
        complete_task(self._session, extract_task, output_ids=[ev.id for ev in evidence])
        self._log(run.id, EventType.EVIDENCE_EXTRACTED, f"{len(evidence)} evidence objects", {"count": len(evidence)})

        # 3) claim construction + relations
        build_task = create_task(self._session, run.id, TaskType.BUILD_CLAIM)
        claims, relations = self._builder.build(evidence)
        claim_repo = SqlClaimRepository(self._session)
        rel_repo = SqlClaimEvidenceRelationRepository(self._session)
        for claim in claims:
            claim_repo.create(claim, run_id=run.id)
        for rel in relations:
            rel_repo.create(rel)
        complete_task(self._session, build_task, output_ids=[c.id for c in claims])
        self._log(run.id, EventType.CLAIM_BUILT, f"{len(claims)} claims, {len(relations)} relations",
                  {"claims": len(claims), "relations": len(relations)})

        # 4) memo
        self._transition(run, RunStatus.SYNTHESIZING, "memo")
        memo = build_memo_from_run(self._session, run.id) or ""
        out_dir = reports_dir or DEFAULT_REPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / f"{run.id}.md"
        report_path.write_text(memo, encoding="utf-8")

        self._transition(run, RunStatus.COMPLETED, "completed")
        self._log(run.id, EventType.RUN_STATE_CHANGED, "vertical slice completed", {"report": str(report_path)})
        return {"run_id": run.id, "status": run.status.value, "memo": memo, "report_path": str(report_path)}
