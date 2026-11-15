"""Assemble one describer from settings (design §7.2).

Only `recorded` is implemented: a real provider needs a client library and a key,
and neither is in scope for S3. Naming an unimplemented provider is a
configuration error rather than a silent fallback, because "I configured OpenAI
and got heuristics" is the kind of quiet failure this project keeps paying for.
"""

from __future__ import annotations

from research_os.config import Settings
from research_os.llm.describer import AsyncProviderDescriber, MethodDescriber
from research_os.llm.recorded import RecordedProvider


def build_describer(settings: Settings) -> MethodDescriber | None:
    name = (settings.llm_provider or "none").strip().lower()
    if name in ("", "none"):
        return None
    if name == "recorded":
        provider = RecordedProvider(settings.llm_fixture_dir)
        return AsyncProviderDescriber(provider, model=settings.llm_model)
    raise ValueError(
        f"llm_provider={settings.llm_provider!r} is not implemented; "
        "use 'none' or 'recorded'"
    )

