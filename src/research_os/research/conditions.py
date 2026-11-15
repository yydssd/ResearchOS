"""Experimental conditions attached to a claim (P5 spec §4.2).

Three properties matter and are easy to get wrong:

- One value per kind. A claim that mentions two backbones does not have a
  backbone; taking the first keeps the field comparable instead of inventing a
  union that matches nothing.
- No defaults. A missing condition stays missing - the P5 cascade treats an
  absent condition as "cannot confirm the setup", never as "same setup".
- Values are normalised to lower case so `Transformer` and `transformer` agree.
"""

from __future__ import annotations

import re

_BACKBONE = re.compile(
    r"\b(transformer|cnn|convolutional|convnet|mamba|u-?net|diffusion)s?\b", re.IGNORECASE
)
_DEGRADATION = re.compile(
    r"\b(?:noise level|level)\s*(\d+)"          # noise level 25 / level 3
    r"|sigma\s*=?\s*(\d+)"                       # sigma=25
    r"|\b(heavy|light|dense|thick|severe|mild|moderate)\b",
    re.IGNORECASE,
)
_BASELINE = re.compile(
    # The connector is case-insensitive because "Compared with MPRNet" opens a
    # sentence; the captured name must stay capitalised so that "compared with
    # the baseline" is not read as a method called "the".
    r"\b(?i:compared (?:with|to)|over)\s+([A-Z][A-Za-z0-9\-]{2,})\b"
)
_TRAINING = re.compile(
    r"\b(from\s+scratch|pre-?train(?:ed|ing)?|fine-?tun(?:ed|ing)?)\b", re.IGNORECASE
)


# Two new kinds for P4's last two dimensions (design §8.1). Both vocabularies are
# closed and both are reused verbatim from the S2 patterns, so a value that enters
# `conditions` here is the same string a `MethodSetup` would carry - one
# vocabulary, two readers.
_SCALE_PARAMS = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?([BM])\b")
_SCALE_GPU = re.compile(r"(\d+)\s?[×x]\s?(A100|H100|V100|GPU|TPU)\b", re.IGNORECASE)
_PROTOCOL = re.compile(r"\b(zero-?shot|few-?shot|\d+-shot|pass@\d+)\b", re.IGNORECASE)


def _scale(text: str) -> str | None:
    """First scale mention, normalised the same way `MethodSetup` does it."""
    options: list[tuple[int, str]] = []
    for match in _SCALE_PARAMS.finditer(text):
        options.append((match.start(), f"{match.group(1)}{match.group(2).lower()}"))
    for match in _SCALE_GPU.finditer(text):
        options.append((match.start(), f"{match.group(1)}x{match.group(2).lower()}"))
    return min(options)[1] if options else None


def _protocol(text: str) -> str | None:
    match = _PROTOCOL.search(text)
    if match is None:
        return None
    return re.sub(r"\s+", "-", match.group(1).lower()).replace("zeroshot", "zero-shot").replace(
        "fewshot", "few-shot"
    )


def extract_condition_map(text: str) -> dict[str, str]:
    """The setup this sentence names, one value per kind, no defaults.

    A dict rather than a tuple because S4 needs to know *which kind* came from
    where: `conditions_from` used to describe the whole tuple, so one new
    high-frequency pattern would overwrite everything the section had established
    (design §8.2). Kinds are always the same six; a missing kind is absent, never
    defaulted.
    """
    found: dict[str, str] = {}

    match = _BACKBONE.search(text)
    if match:
        found["backbone"] = match.group(1).lower().rstrip("s")

    match = _DEGRADATION.search(text)
    if match:
        found["degradation"] = match.group(1) or match.group(2) or match.group(3).lower()

    match = _BASELINE.search(text)
    if match:
        found["baseline"] = match.group(1).lower()

    match = _TRAINING.search(text)
    if match:
        found["training"] = re.sub(r"\s+", "-", match.group(1).lower())

    scale = _scale(text)
    if scale:
        found["scale"] = scale

    protocol = _protocol(text)
    if protocol:
        found["protocol"] = protocol

    return found


def extract_conditions(text: str) -> tuple[str, ...]:
    """`kind=value` strings, sorted by kind. Kept as the tuple contract every
    existing caller and test relies on; new code should use the map."""
    return tuple(f"{kind}={value}" for kind, value in sorted(extract_condition_map(text).items()))
