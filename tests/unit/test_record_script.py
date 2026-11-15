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


def test_an_unresolvable_chunk_id_is_recorded_as_minus_one(tmp_path, monkeypatch):
    """Replay maps -1 to an empty id, which the schema defence rejects. Falling
    back to 0 would attach the quote to the wrong chunk and lose it silently."""
    from research_os.llm.base import MethodDescriptionResponse, MethodPointDraft
    from scripts import record_method_descriptions as script

    class StubProvider:
        async def generate(self, messages, response_model=None):
            return MethodDescriptionResponse(
                points=[MethodPointDraft(aspect="io", statement="s", quote="q", chunk_id="chunk_nope")]
            )

    monkeypatch.setenv("RESEARCHOS_LLM_API_KEY", "test")
    prompt = "[chunk_real] section=Method\nWe store the policy as code."
    payload = __import__("asyncio").run(script._record(StubProvider(), prompt))

    assert payload["points"][0]["prompt_index"] == -1
