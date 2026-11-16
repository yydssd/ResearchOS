"""Which address a stored method point should point at (design §7.4).

The URL is preferred; a locally loaded paper has none, so the local path is the
only address that can be verified. Neither existing must leave the link empty -
a guessed link is worse than a missing one, because the reader cannot tell.
"""

from __future__ import annotations

from research_os.documents.loader import full_text_link
from research_os.domain.models import SourceVersion


def _source(**kwargs) -> SourceVersion:
    return SourceVersion(work_id="w1", source_type="arxiv", title="t", **kwargs)


def test_the_url_wins_when_the_source_has_one():
    source = _source(url="https://arxiv.org/abs/2401.00001", local_path="/tmp/paper.md")
    assert full_text_link(source) == "https://arxiv.org/abs/2401.00001"


def test_a_local_paper_falls_back_to_its_path():
    assert full_text_link(_source(local_path="/tmp/paper.md")) == "/tmp/paper.md"


def test_nothing_to_link_to_stays_none():
    assert full_text_link(_source()) is None
    assert full_text_link(None) is None
