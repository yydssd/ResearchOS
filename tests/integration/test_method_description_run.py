"""L3 end to end (design §7.4/§6.6): points land in the database and the memo
shows them with their section."""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType, FailureType
from research_os.llm.base import DescriptionAttempt, MethodDescriptionResponse, MethodPointDraft
from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlEventRepository, SqlMethodProfileRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
QUOTE = "LangProp, our proposed method, stores each policy as code and scores it by execution feedback."


class QuoteDescriber:
    def __init__(self, quote: str = QUOTE, aspect: str = "mechanism") -> None:
        self._quote = quote
        self._aspect = aspect

    def describe(self, chunks):
        # The quote lives in the Method chunk, not in chunks[0] (that is the
        # Abstract): naming chunks[0] for every point is itself the "unlocatable"
        # case the validator must catch, and it would make the two tests below
        # fail for a reason that has nothing to do with what they assert.
        needle = " ".join(self._quote.split())
        chunk = next(
            (item for item in chunks if needle in " ".join(item.text.split())), chunks[0]
        )
        return DescriptionAttempt(
            response=MethodDescriptionResponse(
                points=[
                    MethodPointDraft(
                        aspect=self._aspect,
                        statement="Stores each policy as code.",
                        quote=self._quote,
                        chunk_id=chunk.id,
                        section=chunk.section,
                    )
                ]
            )
        )


def _run(tmp_path, describer):
    with session_scope() as session:
        supervisor = Supervisor(session, method_describer=describer)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "named_paper.md"), "named", "markdown")],
            reports_dir=tmp_path,
        )
        return run.id


def test_points_are_persisted_and_leave_missing_layers(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber())

    with session_scope() as session:
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert [point.aspect for point in profile.points] == ["mechanism"]
    assert profile.points[0].chunk_id
    assert "L3" not in profile.missing_layers


def test_the_memo_prints_the_point_with_its_section(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber())

    with session_scope() as session:
        memo = build_memo_from_run(session, run_id) or ""

    section = memo.split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "mechanism" in section
    assert "Stores each policy as code" in section


def test_an_unlocatable_quote_is_logged_and_nothing_is_stored(db, tmp_path):
    run_id = _run(tmp_path, QuoteDescriber(quote="This sentence is nowhere in the paper"))

    with session_scope() as session:
        events = [
            event for event in SqlEventRepository(session).list_by_run(run_id)
            if event.failure_type == FailureType.METHOD_POINT_UNLOCATABLE
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert len(events) == 1
    assert events[0].payload["kept"] == 0
    assert profile.points == []
    assert "L3" in profile.missing_layers


def test_no_describer_leaves_l3_missing_without_any_event(db, tmp_path):
    """A run with no key must not pretend a call was attempted."""
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / "named_paper.md"), "named", "markdown")],
            reports_dir=tmp_path,
        )
        events = [
            event for event in SqlEventRepository(session).list_by_run(run.id)
            if event.failure_type in {
                FailureType.METHOD_DESCRIPTION_SKIPPED,
                FailureType.METHOD_DESCRIPTION_REJECTED,
                FailureType.METHOD_POINT_UNLOCATABLE,
                FailureType.METHOD_STATEMENT_UNSUPPORTED,
            }
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run.id)[0]

    assert events == []
    assert "L3" in profile.missing_layers


def test_a_written_point_carries_the_address_of_its_source(db, tmp_path):
    """The point is what survives; the link has to be written with it. This paper
    was loaded from disk, so its URL is empty and the stored path is the only
    address a reader can follow."""
    from research_os.storage.repositories import SqlSourceVersionRepository

    run_id = _run(tmp_path, QuoteDescriber())

    with session_scope() as session:
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]
        source = SqlSourceVersionRepository(session).get(profile.source_version_id)

    assert profile.points, "the fixture quote must yield a point"
    assert source is not None and source.url is None
    assert profile.points[0].source_url == source.local_path
    assert profile.points[0].source_url

