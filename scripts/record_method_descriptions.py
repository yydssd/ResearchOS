"""Record L3 answers for the hold-out corpus (design §7.6).

Requires a real provider, which S3 does not ship: this script fixes the command
line and the exit code so recording is a repeatable command rather than a manual
step, and so the replay path has an obvious place to get its data. It refuses to
run without a provider and records nothing - fabricated L3 answers would look
exactly like measured ones in the audit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / ".holdout_cache"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/method_descriptions"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--provider", required=True, help="provider name to record with")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    print(
        "No provider client is shipped in S3; implement one and pass it here. "
        "Refusing to fabricate recordings.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

