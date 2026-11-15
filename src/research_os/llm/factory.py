"""Assemble one describer from settings (design §7.2).

`recorded` replays fixtures; `openai` talks to any OpenAI-compatible endpoint.
Naming a provider without a key is a configuration error rather than a silent
fallback, because "I configured a model and got heuristics" is the quiet failure
this project keeps paying for.
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
    if name in ("openai", "openai_compatible"):
        if not settings.llm_api_key:
            raise ValueError("llm_provider=openai requires llm_api_key")
        from research_os.llm.openai_compat import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o-mini",
        )
        return AsyncProviderDescriber(provider, model=settings.llm_model)
    raise ValueError(
        f"llm_provider={settings.llm_provider!r} is not implemented; "
        "use 'none', 'recorded' or 'openai'"
    )
