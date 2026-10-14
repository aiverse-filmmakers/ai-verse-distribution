#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiverse_distribution.candidate_evidence import (  # noqa: E402
    CandidateEvidenceError,
    load_candidate_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one immutable AI-Verse Distribution candidate-evidence snapshot."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        payload = load_candidate_evidence(args.path)
    except CandidateEvidenceError as exc:
        print(f"candidate evidence invalid: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "candidate_id": payload["candidate_id"],
                "profile": payload["profile"],
                "components": len(payload["components"]),
                "scope": payload["repository_state"]["scope"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
