"""Block-level scope context for claim identity (P4 spec §4, plan §16).

Identity taken from a single sentence reaches a complete key 0 times in 215 real
claims (10-document probe): papers name the task in the subsection heading
("Classical image SR.") and the dataset in the first sentence of a subsection,
then keep saying "this dataset". So scope is resolved at block level, and the
per-chunk provenance is kept so `inspect-claim` can show where it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from research_os.domain.models import DocumentChunk
from research_os.research.conditions import extract_conditions
from research_os.research.lexicon import DATASETS, TASKS


@dataclass(frozen=True)
class BlockScope:
    """Task/dataset/condition context a claim inherits from its section."""

    task: str | None = None
    datasets: frozenset[str] = frozenset()
    inherited_from: dict[str, str] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()


def _task_of(text: str) -> str | None:
    low = text.lower()
    for phrase, canonical in TASKS:
        if phrase in low:
            return canonical
    return None


_ABSTRACT = re.compile(r"^\s*(?:\d+\.?\s*)?abstract\s*$", re.IGNORECASE)


def _document_task(chunks: list[DocumentChunk]) -> str | None:
    """The paper's own task, used when a heading names none.

    The abstract is read first: a later section may study a second task ("early
    work studied super-resolution in isolation") without that becoming the
    document's task. Falls back to the first chunk that names a task at all.
    """
    for chunk in chunks:
        if _ABSTRACT.match(chunk.section or ""):
            task = _task_of(chunk.text)
            if task:
                return task
    for chunk in chunks:
        task = _task_of(chunk.text)
        if task:
            return task
    return None


def _datasets_of(text: str) -> frozenset[str]:
    low = text.lower()
    return frozenset(d for d in DATASETS if d.lower() in low)


def build_section_scopes(chunks: list[DocumentChunk]) -> dict[str, BlockScope]:
    """Map chunk id -> scope inherited from its section.

    Dataset inheritance is deliberately narrow: a heading that names a dataset
    wins, otherwise only the section's first dataset-naming chunk is inherited.
    That covers "name it once, then say 'this dataset'" and nothing more - no
    pronoun or alias resolution, which would need real coreference.

    Conditions follow the same shape: a heading that names the setup wins,
    otherwise the section's first condition-bearing sentence becomes the
    default for the rest of the section.
    """
    scopes: dict[str, BlockScope] = {}
    sections: dict[tuple[str, str | None], list[DocumentChunk]] = {}
    by_source: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        sections.setdefault((chunk.source_version_id, chunk.section), []).append(chunk)
        by_source.setdefault(chunk.source_version_id, []).append(chunk)
    document_tasks = {sv: _document_task(group) for sv, group in by_source.items()}

    for (source_version, section), group in sections.items():
        heading_task = _task_of(section or "")
        inherited = _datasets_of(section or "")
        provenance: dict[str, str] = {}
        if heading_task:
            provenance["task"] = "heading"
        elif document_tasks.get(source_version):
            provenance["task"] = "document"
        if inherited:
            provenance["datasets"] = "heading"
        else:
            for chunk in group:
                found = _datasets_of(chunk.text)
                if found:
                    inherited = found
                    provenance["datasets"] = "section-first-mention"
                    break
        task = heading_task or document_tasks.get(source_version)
        conditions = extract_conditions(section or "")
        if conditions:
            provenance["conditions"] = "heading"
        else:
            for member in group:
                found_conditions = extract_conditions(member.text)
                if found_conditions:
                    conditions = found_conditions
                    provenance["conditions"] = "section-first-mention"
                    break
        for chunk in group:
            scopes[chunk.id] = BlockScope(task, inherited, dict(provenance), conditions)
    return scopes
