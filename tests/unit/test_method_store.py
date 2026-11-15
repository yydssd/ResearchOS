"""Method profile storage (design §6.5).

Identity is (run_id, source_version_id): a profile is scoped to a run the same
way claims and assessments are (ADR-019), so re-running a question does not
overwrite the previous run's methods.
"""

from __future__ import annotations

from research_os.domain.models import MethodProfile, MethodSetup
from research_os.storage.database import session_scope
from research_os.storage.repositories import SqlMethodProfileRepository


def _profile(svid: str = "sv_1", name: str | None = "LangProp") -> MethodProfile:
    return MethodProfile(
        source_version_id=svid,
        name=name,
        name_quote="We introduce LangProp." if name else None,
        name_chunk_id="chunk_1" if name else None,
        aliases=["Voyager"],
        components=["attention", "gating mechanism"],
        setup=MethodSetup(scale="8xa100", protocol="zero-shot", hyperparameters=["lr=3e-4"]),
        missing_layers=["L3"],
    )


def test_profile_round_trips_with_its_json_columns(db):
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        stored = SqlMethodProfileRepository(session).get("run_1", "sv_1")

    assert stored is not None
    assert stored.name == "LangProp"
    assert stored.name_chunk_id == "chunk_1"
    assert stored.aliases == ["Voyager"]
    assert stored.components == ["attention", "gating mechanism"]
    assert stored.setup.scale == "8xa100"
    assert stored.setup.hyperparameters == ["lr=3e-4"]
    assert stored.missing_layers == ["L3"]


def test_upsert_converges_instead_of_duplicating(db):
    """The vertical slice is re-runnable; a second save must leave one row."""
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(name="LangProp2"), run_id="run_1")
    with session_scope() as session:
        profiles = SqlMethodProfileRepository(session).list_by_run("run_1")

    assert len(profiles) == 1
    assert profiles[0].name == "LangProp2"


def test_two_runs_keep_their_own_profile(db):
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(), run_id="run_1")
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(_profile(name="Other"), run_id="run_2")
    with session_scope() as session:
        first = SqlMethodProfileRepository(session).profiles_for("run_1", ["sv_1"])
        second = SqlMethodProfileRepository(session).profiles_for("run_2", ["sv_1"])

    assert first["sv_1"].name == "LangProp"
    assert second["sv_1"].name == "Other"


def test_profiles_for_is_scoped_to_the_requested_ids(db):
    with session_scope() as session:
        repo = SqlMethodProfileRepository(session)
        repo.upsert(_profile("sv_1"), run_id="run_1")
        repo.upsert(_profile("sv_2", name=None), run_id="run_1")
        found = repo.profiles_for("run_1", ["sv_1", "sv_2", "sv_missing"])

    assert set(found) == {"sv_1", "sv_2"}
    assert found["sv_2"].name is None


def test_points_are_replaced_not_appended(db):
    from research_os.domain.models import MethodPoint

    profile = _profile()
    profile.points = [
        MethodPoint(aspect="goal", statement="Restore all degradations.", quote="q1", chunk_id="chunk_1")
    ]
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(profile, run_id="run_1")
    profile.points = [
        MethodPoint(aspect="mechanism", statement="Fuse maps by gating.", quote="q2", chunk_id="chunk_2")
    ]
    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(profile, run_id="run_1")
    with session_scope() as session:
        stored = SqlMethodProfileRepository(session).get("run_1", "sv_1")

    assert [point.aspect for point in stored.points] == ["mechanism"]
    assert stored.points[0].quote == "q2"
