"""Application configuration (pydantic-settings)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RESEARCHOS_", env_file=".env", extra="ignore")

    app_name: str = "ResearchOS"
    database_url: str = "sqlite:///./research_os.db"
    # Budget defaults (plan §26); the supervisor owns enforcement.
    max_llm_calls: int = 80
    max_search_calls: int = 40
    max_sources_discovered: int = 100
    max_sources_deep_read: int = 20
    max_cost_usd: float = 5.0
    # Comma-separated search providers used by source discovery (plan §14).
    search_providers: str = "arxiv,crossref,openalex"
    # L3 describer (design §7.2). `none` means no describer is assembled at all -
    # not "assembled but broken" - so a run without a key does zero LLM calls and
    # reports L3 as "LLM 未启用" instead of an extraction failure.
    llm_provider: str = "none"  # none | recorded | <provider name>
    llm_model: str | None = None
    llm_api_key: str | None = None
    # Replay directory for `llm_provider="recorded"` (design §7.6).
    llm_fixture_dir: str = "tests/fixtures/method_descriptions"

    @property
    def provider_names(self) -> list[str]:
        """Provider names in configured order, ignoring blanks."""
        return [name.strip() for name in self.search_providers.split(",") if name.strip()]

    @property
    def sqlite_path(self) -> Path | None:
        if self.database_url.startswith("sqlite:///"):
            raw = self.database_url[len("sqlite:///") :]
            if raw and raw != ":memory:":
                return Path(raw)
        return None


settings = Settings()
