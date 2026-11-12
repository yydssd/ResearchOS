"""Repository layer: interfaces + SQLAlchemy implementations.

The database is the single source of truth (invariant 2.4): domain models are
persisted independently, each in its own table.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_os.domain.enums import (
    ClaimStatus,
    ClaimType,
    ConfidenceLabel,
    ContradictionType,
    EvidenceRelation,
    EvidenceType,
    EventType,
    FailureType,
    RunStatus,
    SourceTier,
    SourceType,
    TaskStatus,
    TaskType,
)
from research_os.domain.models import (
    Claim,
    ClaimEvidenceRelation,
    ContradictionAssessment,
    Evidence,
    ResearchEvent,
    ResearchQuestion,
    ResearchRun,
    ResearchTask,
    ResearchWork,
    SourceCandidate,
    SourceVersion,
)
from research_os.storage import tables as t


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


class QuestionRepository(Protocol):
    def create(self, q: ResearchQuestion) -> ResearchQuestion: ...

    def get(self, question_id: str) -> ResearchQuestion | None: ...


class WorkRepository(Protocol):
    def create(self, w: ResearchWork) -> ResearchWork: ...

    def get(self, work_id: str) -> ResearchWork | None: ...


class SourceVersionRepository(Protocol):
    def create(self, sv: SourceVersion, run_id: str | None = None) -> SourceVersion: ...

    def get(self, source_version_id: str) -> SourceVersion | None: ...

    def list_by_work(self, work_id: str) -> list[SourceVersion]: ...

    def list_by_run(self, run_id: str) -> list[SourceVersion]: ...

    def list_all(self) -> list[SourceVersion]: ...


class SourceCandidateRepository(Protocol):
    def create_many(self, candidates: list[SourceCandidate], run_id: str | None = None) -> list[SourceCandidate]: ...

    def list_by_run(self, run_id: str) -> list[SourceCandidate]: ...

    def list_all(self) -> list[SourceCandidate]: ...

    def attach_resolution(self, candidate_id: str, work_id: str, source_version_id: str) -> None: ...


class EvidenceRepository(Protocol):
    def create(self, e: Evidence) -> Evidence: ...

    def get(self, evidence_id: str) -> Evidence | None: ...

    def list_by_source(self, source_version_id: str) -> list[Evidence]: ...

    def list_all(self) -> list[Evidence]: ...


class ClaimRepository(Protocol):
    def create(self, c: Claim, run_id: str | None = None) -> Claim: ...

    def get(self, claim_id: str) -> Claim | None: ...

    def list_by_run(self, run_id: str) -> list[Claim]: ...

    def list_all(self) -> list[Claim]: ...


class ClaimEvidenceRelationRepository(Protocol):
    def create(self, r: ClaimEvidenceRelation) -> ClaimEvidenceRelation: ...

    def list_by_claim(self, claim_id: str) -> list[ClaimEvidenceRelation]: ...

    def list_all(self) -> list[ClaimEvidenceRelation]: ...


class ContradictionRepository(Protocol):
    def create(self, a: ContradictionAssessment) -> ContradictionAssessment: ...

    def list_all(self) -> list[ContradictionAssessment]: ...


class RunRepository(Protocol):
    def create(self, run: ResearchRun) -> ResearchRun: ...

    def get(self, run_id: str) -> ResearchRun | None: ...

    def update(self, run: ResearchRun) -> ResearchRun: ...


class TaskRepository(Protocol):
    def create(self, task: ResearchTask) -> ResearchTask: ...

    def get(self, task_id: str) -> ResearchTask | None: ...

    def list_by_run(self, run_id: str) -> list[ResearchTask]: ...


class EventRepository(Protocol):
    def create(self, event: ResearchEvent) -> ResearchEvent: ...

    def list_by_run(self, run_id: str) -> list[ResearchEvent]: ...


# ---------------------------------------------------------------------------
# SQLAlchemy implementations
# ---------------------------------------------------------------------------


class SqlQuestionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, q: ResearchQuestion) -> ResearchQuestion:
        self._s.add(
            t.QuestionRow(id=q.id, question=q.question, domain=q.domain, constraints=q.constraints)
        )
        return q

    def get(self, question_id: str) -> ResearchQuestion | None:
        row = self._s.get(t.QuestionRow, question_id)
        if row is None:
            return None
        return ResearchQuestion(id=row.id, question=row.question, domain=row.domain, constraints=row.constraints or [])


class SqlWorkRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, w: ResearchWork) -> ResearchWork:
        self._s.add(t.WorkRow(id=w.id, canonical_title=w.canonical_title, authors=w.authors))
        return w

    def get(self, work_id: str) -> ResearchWork | None:
        row = self._s.get(t.WorkRow, work_id)
        if row is None:
            return None
        return ResearchWork(id=row.id, canonical_title=row.canonical_title, authors=row.authors or [])


class SqlSourceVersionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, sv: SourceVersion, run_id: str | None = None) -> SourceVersion:
        self._s.add(
            t.SourceVersionRow(
                id=sv.id,
                work_id=sv.work_id,
                run_id=run_id,
                source_type=sv.source_type.value,
                title=sv.title,
                url=sv.url,
                authors=sv.authors,
                year=sv.year,
                venue=sv.venue,
                doi=sv.doi,
                arxiv_id=sv.arxiv_id,
                version=sv.version,
                verified=sv.verified,
                verification_notes=sv.verification_notes,
                local_path=sv.local_path,
                source_tier=sv.source_tier.value if sv.source_tier else None,
            )
        )
        return sv

    def _to_domain(self, row: t.SourceVersionRow) -> SourceVersion:
        return SourceVersion(
            id=row.id,
            work_id=row.work_id,
            source_type=SourceType(row.source_type),
            title=row.title,
            url=row.url,
            authors=row.authors or [],
            year=row.year,
            venue=row.venue,
            doi=row.doi,
            arxiv_id=row.arxiv_id,
            version=row.version,
            verified=row.verified,
            verification_notes=row.verification_notes or [],
            local_path=row.local_path,
            source_tier=SourceTier(row.source_tier) if row.source_tier else None,
        )

    def get(self, source_version_id: str) -> SourceVersion | None:
        row = self._s.get(t.SourceVersionRow, source_version_id)
        return self._to_domain(row) if row else None

    def list_by_work(self, work_id: str) -> list[SourceVersion]:
        rows = self._s.scalars(select(t.SourceVersionRow).where(t.SourceVersionRow.work_id == work_id)).all()
        return [self._to_domain(r) for r in rows]

    def list_by_run(self, run_id: str) -> list[SourceVersion]:
        rows = self._s.scalars(select(t.SourceVersionRow).where(t.SourceVersionRow.run_id == run_id)).all()
        return [self._to_domain(r) for r in rows]

    def list_all(self) -> list[SourceVersion]:
        rows = self._s.scalars(select(t.SourceVersionRow)).all()
        return [self._to_domain(r) for r in rows]


class SqlSourceCandidateRepository:
    """Persists discovery candidates separately from evidence (plan §14).

    A candidate carries unverified text (title/abstract) for triage only; keeping
    it in its own table is what structurally prevents snippets from becoming
    evidence by accident.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def create_many(self, candidates: list[SourceCandidate], run_id: str | None = None) -> list[SourceCandidate]:
        for c in candidates:
            self._s.add(
                t.SourceCandidateRow(
                    id=c.id,
                    run_id=run_id,
                    provider=c.provider,
                    provider_rank=c.provider_rank,
                    title=c.title,
                    authors=c.authors,
                    year=c.year,
                    venue=c.venue,
                    doi=c.doi,
                    arxiv_id=c.arxiv_id,
                    arxiv_version=c.arxiv_version,
                    url=c.url,
                    abstract=c.abstract,
                    source_type=c.source_type.value,
                    raw=c.raw,
                    resolved_work_id=c.resolved_work_id,
                    resolved_source_version_id=c.resolved_source_version_id,
                )
            )
        return candidates

    def _to_domain(self, row: t.SourceCandidateRow) -> SourceCandidate:
        return SourceCandidate(
            id=row.id,
            provider=row.provider,
            provider_rank=row.provider_rank,
            title=row.title,
            authors=row.authors or [],
            year=row.year,
            venue=row.venue,
            doi=row.doi,
            arxiv_id=row.arxiv_id,
            arxiv_version=row.arxiv_version,
            url=row.url,
            abstract=row.abstract,
            source_type=SourceType(row.source_type),
            raw=row.raw or {},
            resolved_work_id=row.resolved_work_id,
            resolved_source_version_id=row.resolved_source_version_id,
        )

    def list_by_run(self, run_id: str) -> list[SourceCandidate]:
        rows = self._s.scalars(select(t.SourceCandidateRow).where(t.SourceCandidateRow.run_id == run_id)).all()
        return [self._to_domain(r) for r in rows]

    def list_all(self) -> list[SourceCandidate]:
        rows = self._s.scalars(select(t.SourceCandidateRow)).all()
        return [self._to_domain(r) for r in rows]

    def attach_resolution(self, candidate_id: str, work_id: str, source_version_id: str) -> None:
        """Record which work/version a candidate was resolved into (audit trail)."""
        row = self._s.get(t.SourceCandidateRow, candidate_id)
        if row is None:
            raise KeyError(f"candidate {candidate_id} not found")
        row.resolved_work_id = work_id
        row.resolved_source_version_id = source_version_id


class SqlEvidenceRepository:

    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, e: Evidence) -> Evidence:
        self._s.add(
            t.EvidenceRow(
                id=e.id,
                source_version_id=e.source_version_id,
                evidence_type=e.evidence_type.value,
                text=e.text,
                section=e.section,
                page_index=e.page_index,
                page_label=e.page_label,
                table=e.table,
                figure=e.figure,
                chunk_id=e.chunk_id,
                char_start=e.char_start,
                char_end=e.char_end,
                content_hash=e.content_hash,
            )
        )
        return e

    def _to_domain(self, row: t.EvidenceRow) -> Evidence:
        return Evidence(
            id=row.id,
            source_version_id=row.source_version_id,
            evidence_type=EvidenceType(row.evidence_type),
            text=row.text,
            section=row.section,
            page_index=row.page_index,
            page_label=row.page_label,
            table=row.table,
            figure=row.figure,
            chunk_id=row.chunk_id,
            char_start=row.char_start,
            char_end=row.char_end,
            content_hash=row.content_hash,
        )

    def get(self, evidence_id: str) -> Evidence | None:
        row = self._s.get(t.EvidenceRow, evidence_id)
        return self._to_domain(row) if row else None

    def list_by_source(self, source_version_id: str) -> list[Evidence]:
        rows = self._s.scalars(
            select(t.EvidenceRow).where(t.EvidenceRow.source_version_id == source_version_id)
        ).all()
        return [self._to_domain(r) for r in rows]

    def list_all(self) -> list[Evidence]:
        rows = self._s.scalars(select(t.EvidenceRow)).all()
        return [self._to_domain(r) for r in rows]


class SqlClaimRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, c: Claim, run_id: str | None = None) -> Claim:
        self._s.add(
            t.ClaimRow(
                id=c.id,
                run_id=run_id,
                text=c.text,
                claim_type=c.claim_type.value,
                scope=c.scope,
                conditions=c.conditions,
                status=c.status.value,
                confidence_label=c.confidence_label.value,
            )
        )
        return c

    def _to_domain(self, row: t.ClaimRow) -> Claim:
        return Claim(
            id=row.id,
            text=row.text,
            claim_type=ClaimType(row.claim_type),
            scope=row.scope,
            conditions=row.conditions or [],
            status=ClaimStatus(row.status),
            confidence_label=ConfidenceLabel(row.confidence_label),
        )

    def get(self, claim_id: str) -> Claim | None:
        row = self._s.get(t.ClaimRow, claim_id)
        return self._to_domain(row) if row else None

    def list_all(self) -> list[Claim]:
        rows = self._s.scalars(select(t.ClaimRow)).all()
        return [self._to_domain(r) for r in rows]

    def list_by_run(self, run_id: str) -> list[Claim]:
        rows = self._s.scalars(select(t.ClaimRow).where(t.ClaimRow.run_id == run_id)).all()
        return [self._to_domain(r) for r in rows]


class SqlClaimEvidenceRelationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, r: ClaimEvidenceRelation) -> ClaimEvidenceRelation:
        self._s.add(
            t.ClaimEvidenceRelationRow(
                id=f"rel_{r.claim_id[:10]}_{r.evidence_id[:10]}",
                claim_id=r.claim_id,
                evidence_id=r.evidence_id,
                relation=r.relation.value,
                rationale=r.rationale,
            )
        )
        return r

    def _to_domain(self, row: t.ClaimEvidenceRelationRow) -> ClaimEvidenceRelation:
        return ClaimEvidenceRelation(
            claim_id=row.claim_id,
            evidence_id=row.evidence_id,
            relation=EvidenceRelation(row.relation),
            rationale=row.rationale,
        )

    def list_by_claim(self, claim_id: str) -> list[ClaimEvidenceRelation]:
        rows = self._s.scalars(
            select(t.ClaimEvidenceRelationRow).where(t.ClaimEvidenceRelationRow.claim_id == claim_id)
        ).all()
        return [self._to_domain(r) for r in rows]

    def list_all(self) -> list[ClaimEvidenceRelation]:
        rows = self._s.scalars(select(t.ClaimEvidenceRelationRow)).all()
        return [self._to_domain(r) for r in rows]


class SqlContradictionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, a: ContradictionAssessment) -> ContradictionAssessment:
        self._s.add(
            t.ContradictionAssessmentRow(
                id=f"con_{a.claim_a_id[:10]}_{a.claim_b_id[:10]}",
                claim_a_id=a.claim_a_id,
                claim_b_id=a.claim_b_id,
                relationship=a.relationship.value,
                explanation=a.explanation,
                confidence_label=a.confidence_label.value,
            )
        )
        return a

    def _to_domain(self, row: t.ContradictionAssessmentRow) -> ContradictionAssessment:
        return ContradictionAssessment(
            claim_a_id=row.claim_a_id,
            claim_b_id=row.claim_b_id,
            relationship=ContradictionType(row.relationship),
            explanation=row.explanation,
            confidence_label=ConfidenceLabel(row.confidence_label),
        )

    def list_all(self) -> list[ContradictionAssessment]:
        rows = self._s.scalars(select(t.ContradictionAssessmentRow)).all()
        return [self._to_domain(r) for r in rows]


class SqlRunRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, run: ResearchRun) -> ResearchRun:
        self._s.add(
            t.RunRow(
                id=run.id,
                question_id=run.question_id,
                status=run.status.value,
                current_phase=run.current_phase,
                warnings=run.warnings,
                budget=run.budget.model_dump(),
            )
        )
        return run

    def get(self, run_id: str) -> ResearchRun | None:
        row = self._s.get(t.RunRow, run_id)
        if row is None:
            return None
        from research_os.domain.models import ResearchBudget

        return ResearchRun(
            id=row.id,
            question_id=row.question_id,
            status=RunStatus(row.status),
            current_phase=row.current_phase,
            warnings=row.warnings or [],
            budget=ResearchBudget(**row.budget) if row.budget else ResearchBudget(),
        )

    def update(self, run: ResearchRun) -> ResearchRun:
        row = self._s.get(t.RunRow, run.id)
        if row is None:
            raise KeyError(f"run {run.id} not found")
        row.status = run.status.value
        row.current_phase = run.current_phase
        row.warnings = run.warnings
        row.budget = run.budget.model_dump()
        return run


class SqlTaskRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, task: ResearchTask) -> ResearchTask:
        self._s.add(
            t.TaskRow(
                id=task.id,
                run_id=task.run_id,
                task_type=task.task_type.value,
                status=task.status.value,
                input_ids=task.input_ids,
                output_ids=task.output_ids,
                priority=task.priority,
            )
        )
        return task

    def get(self, task_id: str) -> ResearchTask | None:
        row = self._s.get(t.TaskRow, task_id)
        if row is None:
            return None
        return ResearchTask(
            id=row.id,
            run_id=row.run_id,
            task_type=TaskType(row.task_type),
            status=TaskStatus(row.status),
            input_ids=row.input_ids or [],
            output_ids=row.output_ids or [],
            priority=row.priority,
        )

    def list_by_run(self, run_id: str) -> list[ResearchTask]:
        rows = self._s.scalars(select(t.TaskRow).where(t.TaskRow.run_id == run_id)).all()
        return [
            ResearchTask(
                id=r.id,
                run_id=r.run_id,
                task_type=TaskType(r.task_type),
                status=TaskStatus(r.status),
                input_ids=r.input_ids or [],
                output_ids=r.output_ids or [],
                priority=r.priority,
            )
            for r in rows
        ]


class SqlEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, event: ResearchEvent) -> ResearchEvent:
        self._s.add(
            t.EventRow(
                id=event.id,
                run_id=event.run_id,
                event_type=event.event_type.value,
                message=event.message,
                payload=event.payload,
                failure_type=event.failure_type.value if event.failure_type else None,
                created_at=event.created_at,
            )
        )
        return event

    def _to_domain(self, row: t.EventRow) -> ResearchEvent:
        return ResearchEvent(
            id=row.id,
            run_id=row.run_id,
            event_type=EventType(row.event_type),
            message=row.message,
            payload=row.payload or {},
            failure_type=FailureType(row.failure_type) if row.failure_type else None,
            created_at=row.created_at,
        )

    def list_by_run(self, run_id: str) -> list[ResearchEvent]:
        rows = self._s.scalars(select(t.EventRow).where(t.EventRow.run_id == run_id)).all()
        return [self._to_domain(r) for r in rows]
