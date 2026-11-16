"""The memo must show what the method layer got and what it did not (§6.6).

Three lines are mandatory even when they are zero, because "0" and "not counted"
have to be distinguishable to a reader.
"""

from __future__ import annotations

from pathlib import Path

from research_os.orchestration.supervisor import Supervisor
from research_os.reporting.memo import build_memo_from_run
from research_os.storage.database import session_scope

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _memo(tmp_path, paper: str = "named_paper.md") -> str:
    with session_scope() as session:
        supervisor = Supervisor(session)
        run = supervisor.create_run(question_text="Does programmatic policy reuse help?", domain="agent in mc")
        supervisor.run_vertical_slice(
            run_id=run.id,
            sources=[(str(FIXTURES / paper), "named_paper", "markdown")],
            reports_dir=tmp_path,
        )
        return build_memo_from_run(session, run.id) or ""


def test_the_memo_names_the_method_with_its_section(db, tmp_path):
    memo = _memo(tmp_path)
    section = memo.split("# Methods", 1)[1].split("\n# ", 1)[0]

    assert "LangProp" in section
    # The section a name came from is what makes the claim checkable.
    assert "Abstract" in section


def test_the_memo_shows_components_and_setup(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "gating mechanism" in section
    assert "8xa100" in section
    assert "zero-shot" in section


def test_missing_layers_are_printed_as_a_line(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "未获取：L3" in section or "未获取： L3" in section


def test_the_two_attribution_counters_are_present_even_when_zero(db, tmp_path):
    section = _memo(tmp_path).split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "多来源主张：" in section
    assert "未归因主语：" in section


def test_a_paper_with_no_name_says_so_instead_of_staying_silent(db, tmp_path):
    section = _memo(tmp_path, paper="sample_paper.md").split("# Methods", 1)[1].split("\n# ", 1)[0]
    assert "未获取" in section
    assert "L1" in section


def test_a_method_point_shows_where_its_quote_is(db, tmp_path):
    """Full-text linking starts with the offset rendered beside the point; the
    section alone sends the reader hunting through a PDF."""
    from research_os.domain.models import MethodPoint, MethodProfile

    assert MethodProfile.model_fields["points"].annotation is not None
    point = MethodPoint(aspect="io", statement="s", quote="q", chunk_id="c",
                        section="4.2", char_start=8120, char_end=8206)
    assert point.char_start == 8120


def _methods_section(*points) -> str:
    from research_os.domain.models import MethodProfile
    from research_os.reporting.memo import RunGraph, _render_methods_section

    profile = MethodProfile(source_version_id="sv_1", name="LangProp", points=list(points))
    graph = RunGraph(
        run_id="run_1", question_text="q", sources=[], evidence=[], claims=[],
        methods=[profile],
    )
    return "\n".join(_render_methods_section(graph))


def _point(**kwargs):
    from research_os.domain.models import MethodPoint

    return MethodPoint(
        aspect="io", statement="s", quote="q", chunk_id="c", section="4.2",
        char_start=10, char_end=20, **kwargs,
    )


def test_a_point_links_out_to_its_full_text():
    """The location tells the reader where; the link is what lets them go there."""
    section = _methods_section(_point(source_url="https://arxiv.org/abs/2401.00001"))

    assert "chars 10-20]_([source](https://arxiv.org/abs/2401.00001))" in section


def test_a_char_range_read_back_from_sql_still_renders(db):
    """The memo renders profiles loaded from SQL, not the extractor's in-memory
    output, so a range that only survives in memory never reaches the reader."""
    from research_os.domain.models import MethodPoint, MethodProfile
    from research_os.reporting.memo import RunGraph, _render_methods_section
    from research_os.storage.repositories import SqlMethodProfileRepository

    with session_scope() as session:
        SqlMethodProfileRepository(session).upsert(
            MethodProfile(
                source_version_id="sv_1", name="LangProp",
                points=[MethodPoint(aspect="io", statement="s", quote="q", chunk_id="c",
                                    section="4.2", char_start=10, char_end=42)],
            ),
            run_id="run_1",
        )

    with session_scope() as session:
        stored = SqlMethodProfileRepository(session).list_by_run("run_1")

    graph = RunGraph(
        run_id="run_1", question_text="q", sources=[], evidence=[], claims=[],
        methods=stored,
    )
    section = "\n".join(_render_methods_section(graph))

    assert "chars 10-42" in section


def test_a_point_without_a_link_stays_unlinked():
    """No address means no link: an empty `[source]()` would look like a link."""
    section = _methods_section(_point())

    assert "[source](" not in section
    assert "chars 10-20]_" in section
