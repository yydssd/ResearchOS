"""SQLAlchemy ORM table definitions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from research_os.storage.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuestionRow(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    constraints: Mapped[list] = mapped_column(JSON, default=list)


class WorkRow(Base):
    __tablename__ = "works"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSON, default=list)


class SourceVersionRow(Base):
    __tablename__ = "source_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey("works.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_notes: Mapped[list] = mapped_column(JSON, default=list)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SourceCandidateRow(Base):
    """Discovery candidates (plan §14). Kept apart from evidence on purpose."""

    __tablename__ = "source_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_rank: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    arxiv_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="web")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_work_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resolved_source_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(String(64), ForeignKey("source_versions.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), default="text")
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    table: Mapped[str | None] = mapped_column(String(255), nullable=True)
    figure: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ClaimRow(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.id"), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(32), default="factual")
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32))
    confidence_label: Mapped[str] = mapped_column(String(32), default="LOW")


class ClaimEvidenceRelationRow(Base):
    __tablename__ = "claim_evidence_relations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), index=True)
    evidence_id: Mapped[str] = mapped_column(String(64), ForeignKey("evidence.id"), index=True)
    relation: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text, default="")


class ContradictionAssessmentRow(Base):
    __tablename__ = "contradiction_assessments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_a_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), index=True)
    claim_b_id: Mapped[str] = mapped_column(String(64), ForeignKey("claims.id"), index=True)
    relationship: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text, default="")
    confidence_label: Mapped[str] = mapped_column(String(32), default="LOW")


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(64), ForeignKey("questions.id"))
    status: Mapped[str] = mapped_column(String(32), default="CREATED")
    current_phase: Mapped[str] = mapped_column(String(64), default="created")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    budget: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskRow(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    input_ids: Mapped[list] = mapped_column(JSON, default=list)
    output_ids: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
