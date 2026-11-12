"""CLI and API inspection of discovered sources (plan §29 / §28)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_os.cli import main
from research_os.config import settings
from research_os.main import app
from research_os.sources.providers import FixtureProvider
from research_os.storage.database import init_db, session_scope
from research_os.orchestration.supervisor import Supervisor

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "source_candidates"

QUESTION = "Does spatial conditioning improve all-in-one image restoration?"


def _use_temp_db(tmp_path, monkeypatch):
    """Point settings at a throwaway SQLite file so CLI tests never touch the
    project database."""
    db_file = tmp_path / "cli.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file.as_posix()}")
    init_db()


def test_discover_and_sources_commands(tmp_path, monkeypatch, capsys):
    _use_temp_db(tmp_path, monkeypatch)

    assert main(["discover", "--question", QUESTION, "--fixture", str(FIXTURE_DIR)]) == 0
    out = capsys.readouterr().out
    assert "candidates: 7" in out
    # AutoDIR exists in two versions -> 7 candidates collapse into 6 works
    assert "works:      6" in out
    run_id = next(line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("run_id:"))

    assert main(["sources", run_id]) == 0
    listing = capsys.readouterr().out
    assert "AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion  (2 version(s))" in listing
    assert "UNVERIFIED" in listing  # the synthetic web page without identifier


def test_sources_endpoint_exposes_tiers_and_verification(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    with session_scope() as session:
        supervisor = Supervisor(session, providers=[FixtureProvider(FIXTURE_DIR)])
        run = supervisor.create_run(QUESTION)
        supervisor.run_source_discovery(run.id, limit=10, max_queries=1)
        run_id = run.id

    client = TestClient(app)
    response = client.get(f"/research/{run_id}/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_id
    autodir = next(w for w in payload["works"] if "autodir" in w["canonical_title"].lower())
    assert len(autodir["versions"]) == 2
    assert {v["source_tier"] for v in autodir["versions"]} == {"PREPRINT", "OFFICIAL_PUBLICATION"}
    assert all(v["verification_notes"] for v in autodir["versions"])


def test_sources_endpoint_returns_404_for_unknown_run(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    assert TestClient(app).get("/research/run_missing/sources").status_code == 404
