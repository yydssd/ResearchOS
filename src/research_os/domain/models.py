"""Domain models for ResearchOS (Pydantic v2).

Seven core objects from the implementation plan §7, plus the supporting
models needed by orchestration, events, budget, and document loading.
Evidence and claims are deliberately distinct objects (invariant 2.1).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchQuestion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("q"))
    question: str = Field(min_length=3)
    domain: str | None = None
    constraints: list[str] = []

    @field_validator("question")
    @classmethod
    def _question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


class ResearchWork(BaseModel):
    """One logical work, separate from its publication versions."""

    id: str = Field(default_factory=lambda: new_id("w"))
    canonical_title: str = Field(min_length=1)
    authors: list[str] = []


class SourceVersion(BaseModel):
    """A specific version of a work; carries verification state and identifiers."""

    id: str = Field(default_factory=lambda: new_id("sv"))
    work_id: str
    source_type: SourceType
    title: str
    url: str | None = None
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    version: str | None = None
    verified: bool = False
    verification_notes: list[str] = []
    local_path: str | None = None
    # Discovery metadata only (plan §8) — never a truth judgment.
    source_tier: SourceTier | None = None


class SourceCandidate(BaseModel):
    """A search result believed to reference a work (plan §14).

    Candidates are a third kind of object, distinct from both sources and
    evidence: they may contain text (titles, abstracts) that was never verified
    against a real document. Such text must NEVER be promoted into `Evidence`.
    """

    id: str = Field(default_factory=lambda: new_id("cand"))
    provider: str
    provider_rank: int = 0
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    arxiv_version: str | None = None
    url: str | None = None
    # discovery-only text (triage / deep-read hints); never becomes Evidence
    abstract: str | None = None
    source_type: SourceType = SourceType.WEB
    raw: dict = Field(default_factory=dict)
    # filled in after work resolution
    resolved_work_id: str | None = None
    resolved_source_version_id: str | None = None


class Evidence(BaseModel):
    """Must point to an identifiable location — never an LLM summary alone."""

    id: str = Field(default_factory=lambda: new_id("e"))
    source_version_id: str
    evidence_type: EvidenceType = EvidenceType.TEXT
    text: str = Field(min_length=1)
    section: str | None = None
    page_index: int | None = None
    page_label: str | None = None
    table: str | None = None
    figure: str | None = None
    chunk_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("evidence text must not be blank")
        return v.strip()


class QuantitativeEvidence(BaseModel):
    """Structured experimental evidence, kept separate to avoid invalid
    cross-paper comparisons (plan §15).

    `seq` exists because one sentence often reports several metrics
    ("PSNR by 0.42 dB and SSIM by 0.013"); it makes (evidence_id, seq) unique.
    """

    id: str = Field(default_factory=lambda: new_id("qev"))
    evidence_id: str
    seq: int = 0
    dataset: str | None = None
    metric: str | None = None
    method: str | None = None
    value: float | None = None
    comparator: str | None = None
    comparator_value: float | None = None
    protocol: str | None = None
    # The unit attached to this value ("dB"/"percent"). Plan §15 gives `protocol`
    # to the evaluation protocol ("zero-shot"), so a field named protocol holding
    # "dB" made every delta bucket read `dB:0.44` while claiming to be a protocol
    # (`_buckets` does not lowercase). Writer and readers now both use this field;
    # `protocol` stays empty until an evaluation protocol is actually extracted.
    unit: str | None = None
    # A gain stated without naming a metric ("+0.44 dB", "a 0.11 dB improvement").
    # 78% of value-bearing sentences look like this, so without `delta` they would
    # carry no structured fact at all (P4 spec §7).
    delta: float | None = None


class Claim(BaseModel):
    """Status (6 values) + confidence label (4 values); no arbitrary decimal confidence."""

    id: str = Field(default_factory=lambda: new_id("c"))
    text: str = Field(min_length=1)
    claim_type: ClaimType = ClaimType.FACTUAL
    scope: str | None = None
    conditions: list[str] = []
    status: ClaimStatus
    confidence_label: ConfidenceLabel = ConfidenceLabel.LOW
    # Scope identity used for de-duplication (P4). Two claims merge only when this
    # key matches AND the merge gate passes; wording similarity never merges.
    identity_key: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim text must not be blank")
        return v.strip()


class ClaimEvidenceRelation(BaseModel):
    claim_id: str
    evidence_id: str
    relation: EvidenceRelation
    rationale: str = ""


class ContradictionAssessment(BaseModel):
    claim_a_id: str
    claim_b_id: str
    relationship: ContradictionType
    explanation: str = ""
    confidence_label: ConfidenceLabel = ConfidenceLabel.LOW


class ResearchBudget(BaseModel):
    max_llm_calls: int = 80
    max_search_calls: int = 40
    max_sources_discovered: int = 100
    max_sources_deep_read: int = 20
    max_cost_usd: float = 5.0
    # usage counters
    llm_calls: int = 0
    search_calls: int = 0
    sources_discovered: int = 0
    sources_deep_read: int = 0
    cost_usd: float = 0.0

    def exceeded(self) -> bool:
        return (
            self.llm_calls >= self.max_llm_calls
            or self.search_calls >= self.max_search_calls
            or self.sources_discovered >= self.max_sources_discovered
            or self.sources_deep_read >= self.max_sources_deep_read
            or self.cost_usd >= self.max_cost_usd
        )


class ResearchRun(BaseModel):
    """Lightweight run state — the database remains the source of truth."""

    id: str = Field(default_factory=lambda: new_id("run"))
    question_id: str
    status: RunStatus = RunStatus.CREATED
    current_phase: str = "created"
    warnings: list[str] = []
    budget: ResearchBudget = Field(default_factory=ResearchBudget)


class ResearchTask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("t"))
    run_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    input_ids: list[str] = []
    output_ids: list[str] = []
    priority: int = 0


class ResearchContextView(BaseModel):
    """Controlled context view handed to LLM components (invariant 2.4)."""

    question: ResearchQuestion
    task: ResearchTask
    relevant_sources: list[SourceVersion] = []
    relevant_evidence: list[Evidence] = []
    relevant_claims: list[Claim] = []


class ResearchEvent(BaseModel):
    """Structured, persisted event — failures are never silently swallowed."""

    id: str = Field(default_factory=lambda: new_id("ev"))
    run_id: str
    event_type: EventType
    message: str = ""
    payload: dict = Field(default_factory=dict)
    failure_type: FailureType | None = None
    created_at: datetime = Field(default_factory=utcnow)


class DocumentChunk(BaseModel):
    """A provenance-preserving chunk of a source document (plan §15)."""

    id: str = Field(default_factory=lambda: new_id("chunk"))
    source_version_id: str
    page_index: int | None = None
    page_label: str | None = None
    section: str | None = None
    chunk_index: int
    text: str
    content_hash: str = ""

    def compute_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()
