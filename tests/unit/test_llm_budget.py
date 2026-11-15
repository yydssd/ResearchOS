"""Budget accounting for L3 (design §7.3).

`budget.llm_calls` had no writer anywhere in the repo, so `exceeded()` could never
be true for LLM calls: the 80-call ceiling was decoration. These tests pin the
counter and the "check before, add after" order that avoids the 80/81 off-by-one.
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType, FailureType
from research_os.llm.base import MethodDescriptionResponse
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import session_scope
from research_os.storage.repositories import (
    SqlEventRepository,
    SqlMethodProfileRepository,
    SqlRunRepository,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class CountingDescriber:
    """Sync describer that answers with one well-formed point and counts calls."""

    def __init__(self, quote: str) -> None:
        self.calls = 0
        self._quote = quote

    def describe(self, chunks):
        from research_os.llm.base import DescriptionAttempt, MethodPointDraft

        self.calls += 1
        return DescriptionAttempt(
            response=MethodDescriptionResponse(
                points=[
                    MethodPointDraft(
                        aspect="mechanism",
                        statement="Stores each policy as code.",
                        quote=self._quote,
                        chunk_id=chunks[0].id,
                        section=chunks[0].section,
                    )
                ]
            )
        )


def _run(tmp_path, describer, max_llm_calls: int, papers: int = 1) -> tuple[str, int]:
    sources = [(str(FIXTURES / "named_paper.md"), f"p{i}", "markdown") for i in range(papers)]
    with session_scope() as session:
        supervisor = Supervisor(session, method_describer=describer)
        run = supervisor.create_run(question_text="Does reuse help?", domain=None)
        run.budget.max_llm_calls = max_llm_calls
        SqlRunRepository(session).update(run)
        supervisor.run_vertical_slice(run_id=run.id, sources=sources, reports_dir=tmp_path)
        stored = SqlRunRepository(session).get(run.id)
        return run.id, stored.budget.llm_calls


def test_a_zero_budget_makes_no_call_and_says_why(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    run_id, calls = _run(tmp_path, describer, max_llm_calls=0)

    assert calls == 0
    assert describer.calls == 0
    with session_scope() as session:
        events = [
            event
            for event in SqlEventRepository(session).list_by_run(run_id)
            if event.event_type == EventType.FAILURE
            and event.failure_type == FailureType.METHOD_DESCRIPTION_SKIPPED
        ]
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert len(events) == 1
    assert "L3" in profile.missing_layers


def test_the_call_is_counted_after_it_happens(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    _run_id, calls = _run(tmp_path, describer, max_llm_calls=5)

    assert describer.calls == 1
    assert calls == 1


def test_exactly_two_calls_for_three_papers_and_the_third_is_logged(db, tmp_path):
    describer = CountingDescriber("LangProp, our proposed method, stores each policy as code")

    run_id, calls = _run(tmp_path, describer, max_llm_calls=2, papers=3)

    assert describer.calls == 2
    assert calls == 2
    with session_scope() as session:
        skipped = [
            event
            for event in SqlEventRepository(session).list_by_run(run_id)
            if event.failure_type == FailureType.METHOD_DESCRIPTION_SKIPPED
        ]
    assert len(skipped) == 1


def test_a_cost_bearing_provider_accumulates_the_cost(db, tmp_path):
    """A provider that reports usage must move `cost_usd`; one that does not must
    leave it alone rather than invent a number."""

    class Costly(CountingDescriber):
        def describe(self, chunks):
            from research_os.llm.base import DescriptionAttempt

            attempt = super().describe(chunks)
            return DescriptionAttempt(response=attempt.response, cost_usd=0.25)

    describer = Costly("LangProp, our proposed method, stores each policy as code")
    _run_id, _calls = _run(tmp_path, describer, max_llm_calls=5)

    with session_scope() as session:
        stored = SqlRunRepository(session).get(_run_id)
    assert stored.budget.cost_usd == 0.25

