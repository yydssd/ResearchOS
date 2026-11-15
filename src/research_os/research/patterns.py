"""Every pattern the method-acquisition extractors use (design §6.4).

One home for these vocabularies: the name reader, the component reader and the
setup reader all consult the same objects, so they cannot drift into disagreeing
about what a method name looks like.

`GENERIC` always applies. A domain group would be layered on top of it, but no
domain group exists yet: the Minecraft vocabulary is a separate design (design
§12.1), and inventing one here would repeat the mistake that zeroes that domain —
`lexicon.py`'s image-restoration `DATASETS` list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- L1: how a paper names its own method ---------------------------------
# Only explicit naming constructions count. "our method improves PSNR" states no
# name, and the captured token must be capitalised: without that, "we propose a
# method that achieves ..." would hand back "achieves" (design §6.1).
#
# The design lists four constructions; they collapse to three patterns because
# "this work presents X" has the same shape as "we present X", and the first
# pattern already alternates the subject. Two patterns for one sentence would
# count the same name twice.
#
# The apposition requires its closing comma ("X, our method, does ..."). That is
# what separates a real apposition from a discourse marker: "Then, the framework
# is applied" is not a naming sentence, and on the hold-out set it was the only
# false positive this construction produced.
_PROPOSE_VERBS = r"(?i:propose|proposes|introduce|introduces|present|presents|call|calls)"

NAME_CONSTRUCTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "we_verb",
        re.compile(
            rf"\b(?i:we|this paper|this work)\s+{_PROPOSE_VERBS}\s+(?:it\s+)?"
            r"(?P<name>[A-Z][A-Za-z0-9\-]{2,})"
        ),
    ),
    (
        "our_named",
        re.compile(
            r"\b(?i:our)\s+(?i:method|approach|model|framework|system)\s*"
            r"(?:,\s*|\s+(?i:called|named|dubbed)\s+)(?P<name>[A-Z][A-Za-z0-9\-]{2,})"
        ),
    ),
    (
        "apposition",
        re.compile(
            r"(?P<name>[A-Z][A-Za-z0-9\-]{2,})\s*,\s*(?i:our|the)\s+"
            r"(?i:proposed\s+)?(?i:method|approach|model|framework)\s*,"
        ),
    ),
)

# Verbs that appear where a name would, and generic nouns that a naming sentence
# can legitimately capture but that are not names. "We introduce Transformer"
# reads as a name to any regex; the exclusion is what keeps it out.
PREDICATES: frozenset[str] = frozenset(
    {
        "achieves", "achieve", "improves", "improve", "outperforms", "outperform",
        "gains", "gain", "reports", "report", "reduces", "reduce", "increases",
        "increase", "enables", "enable", "yields", "yield", "surpasses", "surpass",
        "demonstrates", "demonstrate", "reaches", "reach", "obtains", "obtain",
        "shows", "show", "uses", "use", "builds", "build",
    }
)
GENERIC_NOUNS: frozenset[str] = frozenset(
    {
        "transformer", "cnn", "convnet", "unet", "gan", "diffusion", "baseline",
        "method", "approach", "model", "framework", "network", "module", "system",
        "attention", "encoder", "decoder", "results", "result", "paper", "work",
    }
)

# --- L2: what counts as a component --------------------------------------
# Structural vocabulary, chosen because these words mean the same thing in an
# image-restoration paper and in a Minecraft-agent paper; unlike a dataset list
# they do not become useless the moment the domain changes (design §6.2).
COMPONENT_WORDS: frozenset[str] = frozenset(
    {
        "encoder", "decoder", "attention", "transformer", "memory", "planner",
        "buffer", "graph", "gate", "adapter", "head", "tokenizer", "retrieval",
    }
)
COMPONENT_PHRASES: tuple[str, ...] = ("reward model",)
COMPONENT_TAILS: tuple[str, ...] = (
    "module", "network", "block", "layer", "branch", "mechanism",
)

# --- L4: reproducible setup ----------------------------------------------
# `protocol` is a closed vocabulary on purpose: "top-1" and "success rate" are
# metrics and "\d+ episodes" is a budget, not an evaluation protocol. Treating a
# metric as a protocol means claiming two claims share a protocol because they
# share a metric (design §6.3).
EVAL_PROTOCOL = re.compile(r"\b(zero-?shot|few-?shot|\d+-shot|pass@\d+)\b", re.IGNORECASE)
# Upper-case B/M only, and never glued to a preceding word or dot, so "0.42 dB"
# and "39.18 dB" cannot read as "42 dB" -> 42B parameters.
SCALE_PARAMS = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([BM])\b")
SCALE_GPU = re.compile(r"(\d+)\s?[×x]\s?(A100|H100|V100|GPU|TPU)\b", re.IGNORECASE)
REPOSITORY_URL = re.compile(r"https?://(?:github\.com|gitlab\.com|huggingface\.co)/[^\s)\]>,;]+")
HYPERPARAMETERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("lr", re.compile(r"(?i)\blearning rate\b[^\d]{0,12}(\d+(?:\.\d+)?(?:[eE]-?\d+)?)")),
    ("batch", re.compile(r"(?i)\bbatch(?: size)?\b[^\d]{0,12}(\d+)")),
    ("epochs", re.compile(r"(?i)\b(\d+)\s+epochs?\b")),
    ("steps", re.compile(r"(?i)\b(\d+)\s+(?:training\s+)?steps?\b")),
    ("optimizer", re.compile(r"(?i)\b(adamw|adam|sgd|rmsprop)\b")),
)


@dataclass(frozen=True)
class DomainPatterns:
    """A domain's extra vocabulary, layered on top of `GENERIC`."""

    name_constructions: tuple[tuple[str, re.Pattern[str]], ...] = ()
    component_words: frozenset[str] = frozenset()
    component_tails: tuple[str, ...] = ()


# Deliberately empty: laying the hook is not the same as filling it (design §6.4).
DOMAINS: dict[str, DomainPatterns] = {}


def domain_patterns(domain: str | None) -> DomainPatterns:
    """Extra patterns for *domain*, or an empty group.

    Callers layer the result on top of the module-level `GENERIC` objects; this
    function never subtracts, so a missing domain degrades to generic-only.
    """
    return DOMAINS.get((domain or "").strip().lower(), DomainPatterns())
