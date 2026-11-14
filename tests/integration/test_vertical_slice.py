"""Week-1 vertical slice integration test (plan §13 / PR2).

fixture question -> fixture paper -> evidence -> claims -> report
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import ClaimStatus, RunStatus
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, collect_run_graph, inspect_claim
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlClaimEvidenceRelationRepository,
    SqlEventRepository,
    SqlRunRepository,
    SqlSourceVersionRepository,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
QUESTION = "Does spatial degradation conditioning provide value beyond ordinary feature conditioning in all-in-one image restoration?"


def test_vertical_slice_end_to_end(db, tmp_path):
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION, domain="image restoration")
        result = supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "sample_paper.md"), "sample_paper", "markdown")],
            reports_dir=tmp_path,
        )

        assert result["status"] == RunStatus.COMPLETED.value
        assert (tmp_path / f"{run.id}.md").exists()

        graph = collect_run_graph(session, run.id)
        assert graph is not None
        assert len(graph.sources) == 1

        # P1 acceptance: at least 3 claims
        assert len(graph.claims) >= 3, f"expected >=3 claims, got {len(graph.claims)}"

        # every supported claim has supporting evidence with a source location
        for claim in graph.claims:
            if claim.status == ClaimStatus.SUPPORTED:
                supporting = graph.supports.get(claim.id, [])
                assert supporting, f"supported claim {claim.id} has no supporting evidence"
                for ev in supporting:
                    assert ev.source_version_id
                    assert ev.page_label or ev.section or ev.chunk_id

        # at least one unsupported/uncertain claim
        unsupported = [c for c in graph.claims if c.status != ClaimStatus.SUPPORTED]
        assert unsupported, "expected at least one unsupported/uncertain claim"

        # memo covers the required sections
        memo = build_memo_from_run(session, run.id)
        for section in [
            "# Research Question",
            "# Executive Conclusion",
            "# Key Findings",
            "# Contradictions and Open Questions",
            "# Uncertainty",
            "# Sources",
        ]:
            assert section in memo, f"memo missing section: {section}"

        # trace chain is queryable: claim -> evidence -> source version -> location
        supported_claim = next(c for c in graph.claims if c.status == ClaimStatus.SUPPORTED)
        info = inspect_claim(session, run.id, supported_claim.id)
        assert info is not None
        assert info["chain"], "claim trace chain must not be empty"
        assert info["chain"][0]["source_version_id"]
        assert info["chain"][0]["source_location"]

        # persistence: relations and events exist
        rels = SqlClaimEvidenceRelationRepository(session).list_all()
        assert len(rels) >= 1
        events = SqlEventRepository(session).list_by_run(run.id)
        assert any(ev.event_type.value == "EVIDENCE_EXTRACTED" for ev in events)
        assert any(ev.event_type.value == "CLAIM_BUILT" for ev in events)


def test_slice_marks_run_failed_when_no_sources(db, tmp_path):
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION)
        result = supervisor.run_vertical_slice(run_id=run.id, sources=[], reports_dir=tmp_path)
        assert result["status"] == RunStatus.FAILED.value
        run_after = SqlRunRepository(session).get(run.id)
        assert run_after.status == RunStatus.FAILED


def test_pdf_source_supported_in_slice(db, tmp_path):
    import fitz

    pdf_path = tmp_path / "paper2.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Our method achieves 39.18 dB PSNR on SIDD and improves Rain100H by 0.42 dB.")
    page.insert_text((72, 110), "We believe future work may extend this to video restoration.")
    doc.save(str(pdf_path))
    doc.close()

    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION)
        result = supervisor.run_vertical_slice(
            run_id=run.id, sources=[(str(pdf_path), "paper2", "pdf")], reports_dir=tmp_path
        )
        assert result["status"] == RunStatus.COMPLETED.value
        sources = SqlSourceVersionRepository(session).list_by_run(run.id)
        assert len(sources) == 1
        assert sources[0].source_type.value == "pdf"
