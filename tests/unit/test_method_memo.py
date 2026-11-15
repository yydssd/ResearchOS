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
