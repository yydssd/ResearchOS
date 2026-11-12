"""Markdown research memo (plan §18).

The memo is derived from the persisted graph — question, sources, evidence,
claims, and claim-evidence relations — so every major finding keeps its
provenance chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from research_os.domain.enums import ClaimStatus, EvidenceRelation
from research_os.domain.models import Claim, Evidence, QuantitativeEvidence, SourceVersion
from research_os.storage.repositories import (
    SqlClaimEvidenceRelationRepository,
    SqlClaimRepository,
    SqlEvidenceRepository,
    SqlQuestionRepository,
    SqlQuantitativeEvidenceRepository,
    SqlRunRepository,
    SqlSourceVersionRepository,
)


@dataclass
class RunGraph:
    run_id: str
    question_text: str
    sources: list[SourceVersion]
    evidence: list[Evidence]
    claims: list[Claim]
    supports: dict[str, list[Evidence]] = field(default_factory=dict)
    counterevidence: dict[str, list[Evidence]] = field(default_factory=dict)
    quantitative: dict[str, list[QuantitativeEvidence]] = field(default_factory=dict)


def collect_run_graph(session: Session, run_id: str) -> RunGraph | None:
    run = SqlRunRepository(session).get(run_id)
    if run is None:
        return None
    question = SqlQuestionRepository(session).get(run.question_id)
    question_text = question.question if question else run.question_id

    sources = SqlSourceVersionRepository(session).list_by_run(run_id)
    source_ids = {s.id for s in sources}
    all_evidence = SqlEvidenceRepository(session).list_all()
    evidence = [e for e in all_evidence if e.source_version_id in source_ids]
    ev_ids = {e.id for e in evidence}

    relations = SqlClaimEvidenceRelationRepository(session).list_all()
    relations = [r for r in relations if r.evidence_id in ev_ids]
    claims = SqlClaimRepository(session).list_by_run(run_id)
    by_id = {e.id: e for e in evidence}

    supports: dict[str, list[Evidence]] = {}
    counter: dict[str, list[Evidence]] = {}
    for r in relations:
        ev = by_id.get(r.evidence_id)
        if ev is None:
            continue
        if r.relation == EvidenceRelation.SUPPORTS:
            supports.setdefault(r.claim_id, []).append(ev)
        elif r.relation == EvidenceRelation.CONTRADICTS:
            counter.setdefault(r.claim_id, []).append(ev)

    quantitative: dict[str, list[QuantitativeEvidence]] = {}
    for fact in SqlQuantitativeEvidenceRepository(session).list_all():
        if fact.evidence_id in ev_ids:
            quantitative.setdefault(fact.evidence_id, []).append(fact)

    return RunGraph(
        run_id=run_id,
        question_text=question_text,
        sources=sources,
        evidence=evidence,
        claims=claims,
        supports=supports,
        counterevidence=counter,
        quantitative=quantitative,
    )


def _confidence_of(claim: Claim) -> str:
    if claim.status == ClaimStatus.UNSUPPORTED:
        return "LOW — no supporting evidence found (heuristic assessment)"
    return claim.confidence_label.value


def _render_text(text: str) -> str:
    """Collapse line breaks for Markdown display only.

    Stored evidence keeps the exact source slice (offsets must stay valid), but a
    quote that wraps mid-sentence would break the memo layout.
    """
    return " ".join(text.split())


def _location(evidence: Evidence) -> str:
    """Human-checkable pointer into the source (plan §2.2).

    Page/section come from the chunk, and the character range lets a reader
    verify the quote verbatim inside the chunk.
    """
    parts = [part for part in (evidence.page_label, evidence.section) if part]
    if evidence.char_start is not None and evidence.char_end is not None:
        parts.append(f"chars {evidence.char_start}-{evidence.char_end}")
    if not parts:
        parts.append(evidence.chunk_id or "unlocated")
    return " · ".join(parts)


def _format_fact_value(fact: QuantitativeEvidence, *, with_metric: bool = True) -> str:
    """Render one numeric fact, including the metric-less delta rows (P4 spec §7).

    A delta row has no metric and often no absolute value: it records "a 0.11 dB
    improvement", which is a gain, not a measurement on a dataset.
    """
    unit = {"dB": " dB", "percent": "%"}.get(fact.protocol or "", "")
    if fact.metric is not None and fact.value is not None:
        prefix = f"{fact.metric} " if with_metric else ""
        return f"{prefix}{fact.value:g}{unit}"
    if fact.delta is not None:
        return f"+{fact.delta:g}{unit} (gain)"
    return "—"


def _quant_suffix(facts: list[QuantitativeEvidence]) -> str:
    if not facts:
        return ""
    rendered = []
    for fact in facts:
        where = f" on {fact.dataset}" if fact.dataset else ""
        rendered.append(f"{_format_fact_value(fact)}{where}")
    return f"  [quant: {'; '.join(rendered)}]"


def _render_quantitative_section(graph: RunGraph) -> list[str]:
    """Group numbers by dataset+metric; ungrouped numbers invite bad comparisons."""
    lines = ["# Quantitative Evidence", ""]
    grouped: dict[tuple[str, str], list[tuple[str, QuantitativeEvidence]]] = {}
    for evidence_id, facts in graph.quantitative.items():
        for fact in facts:
            key = (fact.dataset or "unspecified", fact.metric or fact.protocol or "unspecified")
            grouped.setdefault(key, []).append((evidence_id, fact))

    if not grouped:
        lines.append("- No quantitative values were extracted from the evidence.")
        lines.append("")
        return lines

    lines.append(
        "Values are grouped by dataset and metric: numbers measured on different datasets are "
        "not directly comparable（不可直接比较），so they must not be merged into one ranking."
    )
    lines.append("")
    lines.append("| Dataset | Metric | Value | Comparator | Evidence |")
    lines.append("| --- | --- | --- | --- | --- |")
    for (dataset, metric), items in sorted(grouped.items()):
        for evidence_id, fact in items:
            comparator = "—"
            if fact.comparator_value is not None:
                comparator = f"{fact.comparator_value:g}"
                if fact.comparator:
                    comparator += f" ({fact.comparator})"
            lines.append(f"| {dataset} | {metric} | {_format_fact_value(fact, with_metric=False)} | {comparator} | {evidence_id} |")
    lines.append("")
    return lines


def _grounding_of(claim, graph: RunGraph) -> str:
    """How well a claim's numbers are backed: structured fact, raw value, or none.

    Reported separately from confidence because they fail differently: a claim
    can be well grounded but out of scope, or perfectly scoped with a number no
    extractor could structure.
    """
    supporting = graph.supports.get(claim.id, [])
    if any(graph.quantitative.get(ev.id) for ev in supporting):
        return "structured"
    if "quantitative_unstructured" in (claim.conditions or []):
        return "unstructured"
    return "none"


def _render_kept_separate(claims) -> list[str]:
    """Show the claims that look alike but were deliberately not merged.

    This is the visible evidence that identity-based merging did not collapse
    `A improves Rain100H` into `A improves image restoration` (plan §16).
    """
    lines = ["# Claims Kept Separate", ""]
    groups: dict[tuple[str, str], list] = {}
    for claim in claims:
        if not claim.identity_key:
            continue
        parts = claim.identity_key.split("|")
        if len(parts) < 4:
            continue
        subject, dataset, metrics = parts[0], parts[2], parts[3]
        if not dataset or not metrics:
            continue
        # Key on each metric separately: "psnr,ssim" and "psnr" still share PSNR,
        # and that shared metric is what makes the pair look like a duplicate.
        for metric in metrics.split(","):
            groups.setdefault((subject, metric), []).append((dataset, claim))

    notable = {key: items for key, items in groups.items() if len({ds for ds, _ in items}) > 1}
    if not notable:
        lines.append(
            "- Every claim stands alone in its scope: no two claims shared a subject and "
            "metric while differing in dataset."
        )
        lines.append("")
        return lines

    lines.append(
        "These claims share a subject and a metric but were measured on different scopes, "
        "so they were **not** merged:"
    )
    lines.append("")
    for (subject, metric) in sorted(notable, key=lambda item: (item[1], item[0])):
        for dataset, claim in notable[(subject, metric)]:
            lines.append(
                f"- `{dataset}` · `{metric}` — {_render_text(claim.text)}"
                f"  _(status {claim.status.value}, confidence {claim.confidence_label.value})_"
            )
    lines.append("")
    return lines


def render_memo(graph: RunGraph) -> str:
    lines: list[str] = []
    lines.append("# Research Question")
    lines.append("")
    lines.append(graph.question_text)
    lines.append("")
    lines.append("# Executive Conclusion")
    supported = [c for c in graph.claims if c.status == ClaimStatus.SUPPORTED]
    unsupported = [c for c in graph.claims if c.status != ClaimStatus.SUPPORTED]
    lines.append("")
    lines.append(
        f"This memo reports {len(graph.claims)} claims synthesized from {len(graph.sources)} local source(s) "
        f"and {len(graph.evidence)} evidence objects. {len(supported)} claim(s) are supported by direct "
        f"evidence; {len(unsupported)} claim(s) are marked unsupported/uncertain."
    )
    lines.append("")
    lines.append("# Scope and Search Strategy")
    lines.append("")
    lines.append(
        "Week-1 vertical slice: fixed local sources only. No live search was performed; search snippets "
        "were never used as evidence. Sources are treated as verified local files."
    )
    lines.append("")
    lines.append("# Key Findings")
    lines.append("")
    for i, claim in enumerate(graph.claims, start=1):
        lines.append(f"## Finding {i}")
        lines.append("")
        lines.append(f"**Claim:** {_render_text(claim.text)}")
        lines.append("")
        lines.append(f"- Scope: {claim.scope or 'undetermined'}")
        if claim.conditions:
            lines.append(f"- Conditions: {', '.join(claim.conditions)}")
        lines.append(f"- Grounding: {_grounding_of(claim, graph)}")
        lines.append(f"- Status: {claim.status.value} · Confidence: {_confidence_of(claim)}")
        lines.append("")
        lines.append("**Evidence:**")
        supporting = graph.supports.get(claim.id, [])
        if supporting:
            for ev in supporting:
                lines.append(
                    f"- {_render_text(ev.text)}  _(source {ev.source_version_id}; {_location(ev)})_"
                    f"{_quant_suffix(graph.quantitative.get(ev.id, []))}"
                )
        else:
            lines.append("- _None._")
        counter = graph.counterevidence.get(claim.id, [])
        if counter:
            lines.append("")
            lines.append("**Counterevidence:**")
            for ev in counter:
                lines.append(f"- {_render_text(ev.text)}  _(source {ev.source_version_id}; {_location(ev)})_")
        lines.append("")
    lines.extend(_render_kept_separate(graph.claims))
    lines.extend(_render_quantitative_section(graph))
    lines.append("# Contradictions and Open Questions")
    lines.append("")
    lines.append("- No pairwise contradiction assessment was run in the Week-1 slice (Phase 5).")
    lines.append("")
    lines.append("# Uncertainty")
    lines.append("")
    unsupported_texts = [c.text for c in unsupported]
    if unsupported_texts:
        for t in unsupported_texts:
            lines.append(f"- Unsupported/uncertain: {t}")
    else:
        lines.append("- No unsupported claims detected.")
    lines.append("")
    lines.append("# Candidate Research Gaps")
    lines.append("")
    lines.append("- Live source discovery, verification, and counter-search are planned for Weeks 2–4.")
    lines.append("")
    lines.append("# Sources")
    lines.append("")
    for sv in graph.sources:
        lines.append(f"- {sv.title} ({sv.source_type.value}) — {sv.local_path or sv.url or 'no location'}")
    return "\n".join(lines) + "\n"


def build_memo_from_run(session: Session, run_id: str) -> str | None:
    graph = collect_run_graph(session, run_id)
    if graph is None:
        return None
    return render_memo(graph)


def inspect_claim(session: Session, run_id: str, claim_id: str) -> dict | None:
    """Expose the full trace chain for one claim (invariant 2.2):
    claim -> relation -> evidence -> source version -> location."""
    graph = collect_run_graph(session, run_id)
    if graph is None:
        return None
    claim = next((c for c in graph.claims if c.id == claim_id), None)
    if claim is None:
        return None
    supports = graph.supports.get(claim_id, [])
    sources_by_id = {s.id: s for s in graph.sources}
    chain = []
    for ev in supports:
        sv = sources_by_id.get(ev.source_version_id)
        chain.append(
            {
                "evidence_id": ev.id,
                "evidence_text": ev.text,
                "source_version_id": ev.source_version_id,
                "source_title": sv.title if sv else None,
                "source_location": _location(ev),
                "chunk_id": ev.chunk_id,
                "section": ev.section,
                "page_label": ev.page_label,
                "page_index": ev.page_index,
                "char_range": [ev.char_start, ev.char_end]
                if ev.char_start is not None and ev.char_end is not None
                else None,
                "content_hash": ev.content_hash,
                "quantitative": [
                    {
                        "dataset": fact.dataset,
                        "metric": fact.metric,
                        "value": fact.value,
                        "delta": fact.delta,
                        "comparator_value": fact.comparator_value,
                        "protocol": fact.protocol,
                    }
                    for fact in graph.quantitative.get(ev.id, [])
                ],
                "local_path": sv.local_path if sv else None,
            }
        )
    return {
        "claim_id": claim.id,
        "claim_text": claim.text,
        "status": claim.status.value,
        "confidence": claim.confidence_label.value,
        "scope": claim.scope,
        "conditions": claim.conditions,
        "identity_key": claim.identity_key,
        "grounding": _grounding_of(claim, graph),
        "chain": chain,
    }
