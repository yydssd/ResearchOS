"""The vertical slice stores a method profile per paper (design §6).

Read back from the database rather than from the supervisor's return value: the
point of the layer is that the profile survives the process.
"""

from __future__ import annotations

from pathlib import Path

from research_os.domain.enums import EventType
from research_os.orchestration.supervisor import Supervisor
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlEventRepository, SqlMethodProfileRepository, SqlSourceVersionRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _run(tmp_path, paper: str = "named_paper.md") -> tuple[str, list[str]]:
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does programmatic policy reuse help?", domain="agent in mc")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / paper), "named_paper", "markdown")],
            reports_dir=tmp_path,
        )
        source_ids = [sv.id for sv in SqlSourceVersionRepository(session).list_by_run(run.id)]
        return run.id, source_ids


def test_the_run_persists_one_profile_with_a_name(db, tmp_path):
    run_id, source_ids = _run(tmp_path)

    with session_scope() as session:
        profiles = SqlMethodProfileRepository(session).list_by_run(run_id)

    assert len(profiles) == 1
    assert profiles[0].source_version_id == source_ids[0]
    assert profiles[0].name == "LangProp"
    assert profiles[0].name_chunk_id
    assert "L3" in profiles[0].missing_layers


def test_the_run_persists_the_setup_it_could_read(db, tmp_path):
    run_id, _ = _run(tmp_path)

    with session_scope() as session:
        profile = SqlMethodProfileRepository(session).list_by_run(run_id)[0]

    assert profile.setup.scale == "8xa100"
    assert profile.setup.protocol == "zero-shot"
    assert any(component.endswith("mechanism") for component in profile.components)


def test_an_ambiguous_paper_logs_an_event_instead_of_a_name(db, tmp_path):
    """An unlogged ambiguity is indistinguishable from "no naming sentence",
    which is exactly the confusion `missing_layers` exists to end."""
    paper = tmp_path / "two_names.md"
    paper.write_text(
        "# Two Methods\n\n## Abstract\n\nWe introduce Alpha for control and we "
        "introduce Beta for planning.\n",
        encoding="utf-8",
    )

    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Which method?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id, sources=[(str(paper), "two_names", "markdown")], reports_dir=tmp_path
        )
        events = [
            event
            for event in SqlEventRepository(session).list_by_run(run.id)
            if event.event_type == EventType.METHOD_NAME_AMBIGUOUS
        ]
        profiles = SqlMethodProfileRepository(session).list_by_run(run.id)

    assert len(events) == 1
    assert events[0].failure_type is None  # ordinary event, not a failure (design §7.5)
    assert sorted(events[0].payload["candidates"]) == ["Alpha", "Beta"]
    assert profiles[0].name is None


def test_a_second_paper_on_the_same_run_gets_its_own_profile(db, tmp_path):
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Two papers?", domain=None)
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[
                (str(FIXTURES / "named_paper.md"), "named", "markdown"),
                (str(FIXTURES / "sample_paper.md"), "sample", "markdown"),
            ],
            reports_dir=tmp_path,
        )
        profiles = SqlMethodProfileRepository(session).list_by_run(run.id)

    assert len(profiles) == 2
    assert {profile.name for profile in profiles} == {"LangProp", None}
