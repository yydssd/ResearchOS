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


def extract_conditions(text: str) -> tuple[str, ...]:
    """Return the setup this sentence names, sorted by kind, at most one each."""
    found: set[str] = set()

    match = _BACKBONE.search(text)
    if match:
        found.add(f"backbone={match.group(1).lower().rstrip('s')}")

    match = _DEGRADATION.search(text)
    if match:
        value = match.group(1) or match.group(2) or match.group(3).lower()
        found.add(f"degradation={value}")

    match = _BASELINE.search(text)
    if match:
        found.add(f"baseline={match.group(1).lower()}")

    match = _TRAINING.search(text)
    if match:
        found.add("training=" + re.sub(r"\s+", "-", match.group(1).lower()))

    return tuple(sorted(found))
