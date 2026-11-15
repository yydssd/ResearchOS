"""P3 acceptance: evidence quality end to end (plan §15).

fixture paper -> persisted chunks -> evidence with exact offsets -> quantitative
rows -> memo; plus the provenance gate that refuses unlocatable evidence.
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import FailureType, RunStatus
from research_os.domain.models import Evidence
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run, inspect_claim
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlChunkRepository,
    SqlClaimRepository,
    SqlEventRepository,
    SqlEvidenceRepository,
    SqlQuantitativeEvidenceRepository,
    SqlSourceVersionRepository,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
QUESTION = "Does spatial degradation conditioning provide value in all-in-one image restoration?"


def test_slice_persists_chunks_exact_offsets_and_quantitative_facts(db, tmp_path):
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION, domain="image restoration")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "sample_paper.md"), "sample_paper", "markdown")],
            reports_dir=tmp_path,
        )

        source = SqlSourceVersionRepository(session).list_by_run(run.id)[0]
        chunks = SqlChunkRepository(session).list_by_source(source.id)
        evidence = SqlEvidenceRepository(session).list_all()
        assert chunks and evidence

        # every evidence reference resolves, and the offsets reproduce the quote
        chunks_by_id = {c.id: c for c in chunks}
        for ev in evidence:
            assert ev.chunk_id in chunks_by_id, "evidence references a chunk that was never stored"
            chunk = chunks_by_id[ev.chunk_id]
            assert chunk.text[ev.char_start : ev.char_end] == ev.text

        # quantitative rows exist and carry dataset/metric/value
        facts = SqlQuantitativeEvidenceRepository(session).list_all()
        assert len(facts) >= 3
        assert {"Rain100H", "SIDD"} <= {f.dataset for f in facts}
        psnr_sidd = next(f for f in facts if f.dataset == "SIDD" and f.metric == "PSNR")
        assert psnr_sidd.value == 39.18
        assert psnr_sidd.comparator_value == 39.01
        assert psnr_sidd.unit == "dB"

        memo = build_memo_from_run(session, run.id)
        assert "# Quantitative Evidence" in memo
        assert "39.18" in memo
        # The evidence quote inside the memo also contains "39.18 dB", so only the
        # [quant: ...] segment proves the renderer used `unit`: with `fact.protocol`
        # that segment degrades to "PSNR 39.18" and this assertion fails.
        assert "[quant: PSNR 39.18 dB on SIDD]" in memo
        assert "不可直接比较" in memo

        # trace chain now exposes chunk-level provenance
        for claim in SqlClaimRepository(session).list_by_run(run.id):
            info = inspect_claim(session, run.id, claim.id)
            if info and info["chain"]:
                entry = info["chain"][0]
                assert entry["chunk_id"]
                assert entry["char_range"]
                assert entry["section"] or entry["page_label"]
                break
        else:  # pragma: no cover - the slice always yields at least one supported claim
            raise AssertionError("no claim with supporting evidence was produced")


def test_html_source_keeps_section_provenance(db, tmp_path):
    page = tmp_path / "project_page.html"
    page.write_text(
        "<html><body><nav>menu</nav><h1>Method</h1>"
        "<p>Our method achieves 39.18 dB PSNR on SIDD compared with 39.01 dB for the baseline model.</p>"
        "<h2>Limitations</h2><p>We believe the effect may diminish on easier benchmarks such as Rain100L.</p>"
        "</body></html>",
        encoding="utf-8",
    )

    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text=QUESTION)
        supervisor.run_vertical_slice(
            run_id=run.id, sources=[(str(page), "project_page", "html")], reports_dir=tmp_path
        )

        source = SqlSourceVersionRepository(session).list_by_run(run.id)[0]
        assert source.source_type.value == "html"
        chunks = SqlChunkRepository(session).list_by_source(source.id)
        assert {c.section for c in chunks} == {"Method", "Limitations"}
        assert all(c.page_label == "html" for c in chunks)

        facts = SqlQuantitativeEvidenceRepository(session).list_all()
        assert any(f.dataset == "SIDD" and f.value == 39.18 for f in facts)


def test_evidence_without_location_is_rejected_and_logged(db, tmp_path):
    class _NoLocationExtractor:
        def extract(self, chunks):
            return [
                Evidence(
                    source_version_id=chunks[0].source_version_id,
                    text="A sentence that carries no locatable position inside the source document.",
                )
            ]

    with session_scope() as session:
        supervisor = Supervisor(session, evidence_extractor=_NoLocationExtractor())
        run = supervisor.create_run(question_text=QUESTION)
        result = supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "sample_paper.md"), "sample_paper", "markdown")],
            reports_dir=tmp_path,
        )

        assert result["status"] == RunStatus.COMPLETED.value
        assert SqlEvidenceRepository(session).list_all() == []

        failures = [
            event
            for event in SqlEventRepository(session).list_by_run(run.id)
            if event.failure_type == FailureType.CITATION_LOCATION_MISSING
        ]
        assert failures, "rejected evidence must leave a typed failure event"
        assert any("CITATION_LOCATION_MISSING" in warning for warning in supervisor.get_run(run.id).warnings)
