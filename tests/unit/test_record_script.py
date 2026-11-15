"""Recording is a command, not a manual step (design §7.6)."""

from __future__ import annotations

import json

from scripts.record_method_descriptions import plan_jobs, write_recording


def test_jobs_are_keyed_by_the_prompt_without_ids():
    from research_os.domain.models import DocumentChunk

    chunks = [DocumentChunk(id="chunk_x", source_version_id="sv", section="Method",
                            chunk_index=0, text="We store the policy as code.")]
    jobs = plan_jobs([chunks])

    assert len(jobs) == 1
    key, prompt = jobs[0]
    assert "chunk_x" not in key          # the key must survive a new run
    assert "[chunk_x]" in prompt          # the prompt still carries the real id


def test_an_existing_recording_is_not_overwritten(tmp_path):
    key = "abc123"
    out = tmp_path / f"{key}.json"
    out.write_text(json.dumps({"points": [{"quote": "kept"}]}), encoding="utf-8")

    write_recording(tmp_path, key, {"points": [{"quote": "new"}]})

    assert json.loads(out.read_text(encoding="utf-8"))["points"][0]["quote"] == "kept"


def test_no_key_means_exit_2_and_no_files(tmp_path, monkeypatch):
    from scripts import record_method_descriptions as script

    # Explicit: a developer shell with a real key exported must not turn the
    # "refuse to fabricate" contract into a 40-paper recording run.
    monkeypatch.delenv("RESEARCHOS_LLM_API_KEY", raising=False)
    code = script.main(["--provider", "openai", "--out", str(tmp_path), "--cache", str(tmp_path)])

    assert code == 2
    assert list(tmp_path.glob("*.json")) == []
