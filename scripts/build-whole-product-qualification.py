#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aiverse_distribution.whole_product_qualification import (  # noqa: E402
    WholeProductQualificationError,
    build_whole_product_qualification,
)


def _load(path: Path, label: str):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WholeProductQualificationError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise WholeProductQualificationError(f"{label} must be a JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build read-only whole-product qualification evidence for one admitted candidate."
    )
    parser.add_argument("candidate_id")
    parser.add_argument("--preservation", required=True, type=Path)
    parser.add_argument("--composed-acceptance", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        result = build_whole_product_qualification(
            ROOT,
            args.candidate_id,
            _load(args.preservation, "preservation result"),
            _load(args.composed_acceptance, "composed acceptance"),
        )
    except WholeProductQualificationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(json.dumps({"valid": True, "candidate_id": args.candidate_id, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
