"""Record L3 answers for the hold-out corpus (design §7.6).

Without `RESEARCHOS_LLM_API_KEY` this exits 2 and writes nothing: fabricated L3
data would be indistinguishable from measured data in the audit (known limit 17).

Recordings are keyed by `prompt_key` (the prompt without its per-run chunk ids)
and each point carries `prompt_index`, so a replay on a later run maps onto that
run's real chunk ids.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from research_os.documents.chunks import chunk_pages
from research_os.documents.html import load_html
from research_os.llm.base import Message
from research_os.llm.describer import SYSTEM_PROMPT, build_prompt
from research_os.llm.openai_compat import OpenAICompatibleProvider
from research_os.llm.recorded import prompt_ids, prompt_key

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / ".holdout_cache"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/method_descriptions"


def plan_jobs(per_paper_chunks: list[list]) -> list[tuple[str, str]]:
    """(key, prompt) per paper. The key drops ids so it survives a new run."""
    return [(prompt_key(build_prompt(chunks)), build_prompt(chunks)) for chunks in per_paper_chunks]


def write_recording(out_dir: Path, key: str, payload: dict) -> Path:
    """Write once: a recording is a measurement, not a cache."""
    path = out_dir / f"{key}.json"
    if path.exists():
        return path
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def _record(provider, prompt: str) -> dict:
    response = await provider.generate(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=prompt)]
    )
    # Same parser as the replay side: a chunk body line that happens to start
    # with "[chunk_" would otherwise shift every index by one and attach each
    # quote to the wrong chunk on the next run.
    ids = prompt_ids(prompt)
    points = []
    for point in response.points:
        # -1, not 0: an id the prompt does not carry is not "the first chunk".
        # Replay turns -1 into an empty chunk_id, which the schema defence
        # rejects - a wrong chunk would be worse than none (recorded.py's rule).
        index = ids.index(point.chunk_id) if point.chunk_id in ids else -1
        points.append(
            {
                "aspect": point.aspect,
                "statement": point.statement,
                "quote": point.quote,
                "prompt_index": index,
                "section": point.section,
            }
        )
    return {"points": points}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ids-file", type=Path, default=None)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    if args.provider not in ("openai", "openai_compatible"):
        print(f"provider {args.provider!r} is not implemented; use 'openai'", file=sys.stderr)
        return 2
    api_key = os.environ.get("RESEARCHOS_LLM_API_KEY")
    if not api_key:
        print("RESEARCHOS_LLM_API_KEY is not set; refusing to fabricate recordings.", file=sys.stderr)
        return 2

    ids = [
        line.strip()
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if args.ids_file else sorted(path.stem for path in args.cache.glob("*.html"))
    if args.limit:
        ids = ids[: args.limit]

    provider = OpenAICompatibleProvider(
        base_url=os.environ.get("RESEARCHOS_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=api_key,
        model=os.environ.get("RESEARCHOS_LLM_MODEL", "gpt-4o-mini"),
    )
    recorded = 0
    for arxiv_id in ids:
        path = args.cache / f"{arxiv_id}.html"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            continue
        chunks = chunk_pages(load_html(path), f"sv_{arxiv_id}")
        key, prompt = plan_jobs([chunks])[0]
        if (args.out / f"{key}.json").exists():
            continue
        write_recording(args.out, key, asyncio.run(_record(provider, prompt)))
        recorded += 1
    print(f"recorded {recorded} of {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
