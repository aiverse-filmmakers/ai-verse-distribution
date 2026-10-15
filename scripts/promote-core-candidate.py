#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from aiverse_distribution.core_promotion import (
    CorePromotionError,
    apply_core_promotion,
    plan_core_promotion,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly apply one evidence-bound Core candidate promotion."
    )
    parser.add_argument("candidate_id")
    parser.add_argument("--root", default=".")
    parser.add_argument("--qualification-ref", required=True)
    parser.add_argument("--registry-snapshot", required=True)
    parser.add_argument("--repository-state-snapshot", required=True)
    parser.add_argument("--mode", choices=("normal", "emergency"), default="normal")
    parser.add_argument("--emergency-reason")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate the existing Core promotion/candidate catalogs and write promotion evidence.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    registry = Path(args.registry_snapshot).read_bytes()
    state = Path(args.repository_state_snapshot).read_bytes()
    try:
        if args.apply:
            result = apply_core_promotion(
                root,
                args.candidate_id,
                args.qualification_ref,
                registry,
                state,
                mode=args.mode,
                emergency_reason=args.emergency_reason,
            )
        else:
            result = plan_core_promotion(
                root,
                args.candidate_id,
                args.qualification_ref,
                registry,
                state,
                mode=args.mode,
                emergency_reason=args.emergency_reason,
            )
    except (CorePromotionError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 1

    evidence = result["promotion_evidence"]
    print(
        json.dumps(
            {
                "valid": True,
                "applied": bool(args.apply),
                "release_id": result["release_id"],
                "previous_release_id": result["previous_release_id"],
                "mode": result["mode"],
                "system_sync": evidence["system_sync"],
                "writes": evidence["writes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
