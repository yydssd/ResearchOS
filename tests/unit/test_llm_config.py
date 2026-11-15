"""Wiring by configuration, not by import side effects (design §7.2).

`UnavailableProvider` was never instantiated anywhere; the honest default is "no
describer at all", so a run with no key does zero calls and says so.
"""

from __future__ import annotations

from research_os.config import Settings
from research_os.llm.describer import AsyncProviderDescriber
from research_os.llm.factory import build_describer


def test_no_provider_means_no_describer():
    settings = Settings(llm_provider="none")
    assert build_describer(settings) is None


def test_an_unknown_provider_name_is_a_configuration_error():
    settings = Settings(llm_provider="openai")
    try:
        build_describer(settings)
    except ValueError as exc:
        assert "llm_provider" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("an unimplemented provider name must not build silently")


def test_the_recorded_provider_builds_a_describer():
    settings = Settings(llm_provider="recorded", llm_fixture_dir="tests/fixtures/method_descriptions")
    describer = build_describer(settings)
    assert isinstance(describer, AsyncProviderDescriber)

