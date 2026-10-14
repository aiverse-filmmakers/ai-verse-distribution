#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiverse_distribution.candidate_admission import (  # noqa: E402
    CandidateAdmissionError,
    validate_candidate_admission,
)


def main() -> int:
    try:
        admitted = validate_candidate_admission(ROOT)
    except CandidateAdmissionError as exc:
        print(f"candidate admission invalid: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "candidate_count": len(admitted),
                "candidates": admitted,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
