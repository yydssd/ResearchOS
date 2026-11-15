"""Repository persistence tests (P0 acceptance)."""

from __future__ import annotations

from research_os.domain.enums import (
    ClaimStatus,
    EvidenceRelation,
    EventType,
    RunStatus,
    SourceType,
    TaskStatus,
    TaskType,
)
from research_os.domain.models import (
    Claim,
    ClaimEvidenceRelation,
    Evidence,
    QuantitativeEvidence,
    ResearchEvent,
    ResearchQuestion,
    ResearchRun,
    ResearchTask,
    ResearchWork,
    SourceVersion,
)
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlClaimEvidenceRelationRepository,
    SqlClaimRepository,
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlQuantitativeEvidenceRepository,
    SqlQuestionRepository,
    SqlRunRepository,
    SqlSourceVersionRepository,
    SqlTaskRepository,
    SqlWorkRepository,
)


def test_question_roundtrip(db):
    with session_scope() as s:
        q = ResearchQuestion(question="Which method improves restoration?", domain="image restoration")
        SqlQuestionRepository(s).create(q)
    with session_scope() as s:
        got = SqlQuestionRepository(s).get(q.id)
        assert got is not None and got.question == "Which method improves restoration?" and got.domain == "image restoration"


def test_work_source_version_relationship(db):
    """One logical work has multiple source versions (plan §7.2)."""
    with session_scope() as s:
        work = ResearchWork(canonical_title="Paper A", authors=["A", "B"])
        SqlWorkRepository(s).create(work)
        sv1 = SourceVersion(work_id=work.id, source_type=SourceType.ARXIV, title="Paper A (arXiv v1)", version="v1")
        sv2 = SourceVersion(work_id=work.id, source_type=SourceType.CONFERENCE, title="Paper A (Conf 2024)")
        repo = SqlSourceVersionRepository(s)
        repo.create(sv1)
        repo.create(sv2)
    with session_scope() as s:
        versions = SqlSourceVersionRepository(s).list_by_work(work.id)
        assert len(versions) == 2
        assert {v.source_type.value for v in versions} == {"arxiv", "conference"}


def test_evidence_and_claim_persistence(db):
    with session_scope() as s:
        work = ResearchWork(canonical_title="W")
        SqlWorkRepository(s).create(work)
        sv = SourceVersion(work_id=work.id, source_type=SourceType.PDF, title="W.pdf", local_path="x.pdf")
        SqlSourceVersionRepository(s).create(sv)
        ev = Evidence(source_version_id=sv.id, text="A improves Rain100H PSNR by 0.42 dB.")
        SqlEvidenceRepository(s).create(ev)
        claim = Claim(text="A improves Rain100H PSNR", status=ClaimStatus.SUPPORTED)
        SqlClaimRepository(s).create(claim)
        rel = ClaimEvidenceRelation(
            claim_id=claim.id, evidence_id=ev.id, relation=EvidenceRelation.SUPPORTS, rationale="direct"
        )
        SqlClaimEvidenceRelationRepository(s).create(rel)
    with session_scope() as s:
        assert SqlEvidenceRepository(s).get(ev.id) is not None
        assert SqlEvidenceRepository(s).list_by_source(sv.id)[0].id == ev.id
        got = SqlClaimRepository(s).get(claim.id)
        assert got is not None and got.status == ClaimStatus.SUPPORTED
        rels = SqlClaimEvidenceRelationRepository(s).list_by_claim(claim.id)
        assert rels[0].evidence_id == ev.id
        assert rels[0].relation == EvidenceRelation.SUPPORTS


def test_run_and_task_persistence(db):
    with session_scope() as s:
        run = ResearchRun(question_id="q_1")
        SqlRunRepository(s).create(run)
        task = ResearchTask(run_id=run.id, task_type=TaskType.EXTRACT_EVIDENCE, status=TaskStatus.RUNNING)
        SqlTaskRepository(s).create(task)
    with session_scope() as s:
        got = SqlRunRepository(s).get(run.id)
        assert got is not None and got.status.value == "CREATED"
        tasks = SqlTaskRepository(s).list_by_run(run.id)
        assert tasks[0].task_type == TaskType.EXTRACT_EVIDENCE


def test_run_state_transition(db):
    with session_scope() as s:
        run = ResearchRun(question_id="q_1")
        SqlRunRepository(s).create(run)
        run.status = RunStatus.PLANNING
        run.current_phase = "planning"
        SqlRunRepository(s).update(run)
    with session_scope() as s:
        got = SqlRunRepository(s).get(run.id)
        assert got.status.value == "PLANNING" and got.current_phase == "planning"


def test_event_persistence(db):
    with session_scope() as s:
        event = ResearchEvent(run_id="run_1", event_type=EventType.RUN_CREATED, message="created", payload={"a": 1})
        SqlEventRepository(s).create(event)
    with session_scope() as s:
        events = SqlEventRepository(s).list_by_run("run_1")
        assert len(events) == 1
        assert events[0].event_type == EventType.RUN_CREATED
        assert events[0].payload == {"a": 1}


def test_quantitative_evidence_keeps_unit_apart_from_protocol(db):
    """If `unit` had no column, the write would drop it silently and the read would
    return None while `protocol` still looked correct — a loss no protocol-only
    assertion would catch. Both a row carrying a unit and a legacy row without one
    must therefore come back unchanged."""
    with session_scope() as s:
        work = ResearchWork(canonical_title="W")
        SqlWorkRepository(s).create(work)
        sv = SourceVersion(work_id=work.id, source_type=SourceType.PDF, title="W.pdf", local_path="x.pdf")
        SqlSourceVersionRepository(s).create(sv)
        ev = Evidence(source_version_id=sv.id, text="PSNR 39.18 dB on SIDD.")
        SqlEvidenceRepository(s).create(ev)
        SqlQuantitativeEvidenceRepository(s).create_many(
            [
                QuantitativeEvidence(
                    evidence_id=ev.id, seq=0, dataset="SIDD", metric="PSNR",
                    value=39.18, unit="dB", protocol="zero-shot",
                ),
                # The shape of a row written before the column existed: no unit.
                QuantitativeEvidence(
                    evidence_id=ev.id, seq=1, dataset="SIDD", metric="PSNR",
                    value=39.50,
                ),
            ]
        )
    with session_scope() as s:
        # `list_all` has no ORDER BY, so key on seq instead of trusting row order.
        by_seq = {r.seq: r for r in SqlQuantitativeEvidenceRepository(s).list_all()}
        assert len(by_seq) == 2
        assert by_seq[0].unit == "dB"
        assert by_seq[0].protocol == "zero-shot"
        assert by_seq[1].unit is None
        assert by_seq[1].value == 39.50
