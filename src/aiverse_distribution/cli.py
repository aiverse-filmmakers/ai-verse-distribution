from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from .adapters import UnsupportedLifecycle
from .release_catalog import DistributionError, ReleaseBlockedError
from .diagnostics import create_support_bundle
from .orchestrator import Orchestrator
from .process import ProcessError


def _emit(payload: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    if isinstance(payload, dict):
        if "state" in payload:
            print(f"state: {payload['state']}")
        if "release_set_id" in payload:
            print(f"release set: {payload['release_set_id']}")
        if "profile" in payload:
            print(f"profile: {payload['profile']}")
        if "root" in payload:
            print(f"root: {payload['root']}")
        components = payload.get("components")
        if isinstance(components, dict):
            for cid, item in components.items():
                if isinstance(item, dict):
                    print(f"{cid}: {item.get('state', 'ok' if item.get('ok') else 'reported')}")
        if "changes" in payload:
            if payload["changes"]:
                for item in payload["changes"]:
                    print(f"{item['component']}: {item.get('from')} -> {item.get('to')}")
            else:
                print("No release-set changes.")
        if "results" in payload and not components:
            print("completed")
        if "next" in payload:
            for item in payload["next"]:
                print(item)
        return
    print(payload)


def _choose_profile(explicit: Optional[str]) -> str:
    if explicit:
        return explicit.lower()
    if not sys.stdin.isatty():
        return "core"
    print("Choose AI-Verse profile:")
    print("  1. Core")
    print("  2. Agent")
    print("  3. Full")
    print("  4. Custom")
    value = input("Profile [1]: ").strip() or "1"
    return {"1": "core", "2": "agent", "3": "full", "4": "custom"}.get(value, value.lower())


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aiverse", description="AI-Verse one-product Distribution CLI")
    p.add_argument("--version", action="store_true", help="show Distribution version")
    sub = p.add_subparsers(dest="command")

    q = sub.add_parser("install", help="install an exact compatible AI-Verse release set")
    q.add_argument("--profile", choices=["core", "agent", "full", "custom"])
    q.add_argument("--component", action="append", default=[])
    q.add_argument("--release-set")
    q.add_argument("--root", default=str(Path.home() / "AI-Verse"))
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("setup", help="run owner-controlled setup for the locked profile")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("onboard", help="hand off to owner onboarding without inventing Brain intent")
    q.add_argument("--brain-answers", type=Path)
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("status", help="show live owner-backed state")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("doctor", help="run deep component and composed-system verification")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("component", help="run one component lifecycle operation")
    q.add_argument(
        "action",
        choices=["install", "setup", "status", "doctor", "enable", "disable", "update", "uninstall"],
    )
    q.add_argument("component")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("update", help="preview or apply a compatible release-set update")
    q.add_argument("--to", dest="release_set")
    q.add_argument("--apply", action="store_true")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("rollback", help="preview or apply rollback to a known compatible release set")
    q.add_argument("--to", dest="release_set", required=True)
    q.add_argument("--apply", action="store_true")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("support-bundle", help="create redacted structured diagnostics")
    q.add_argument("--output", type=Path)
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("open", help="show the installed AI-Verse root and use handoff")
    q.add_argument("--json", action="store_true")

    q = sub.add_parser("releases", help="show admitted release sets")
    q.add_argument("--json", action="store_true")

    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    from . import __version__

    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.version:
        print(__version__)
        return 0
    if not args.command:
        parser.print_help()
        return 0

    app = Orchestrator()
    try:
        if args.command == "install":
            profile = _choose_profile(args.profile)
            payload = app.install(
                profile=profile,
                root=Path(args.root),
                release_set_id=args.release_set,
                components=args.component,
            )
            _emit(payload, args.json)
            return 0

        if args.command == "setup":
            payload = app.setup()
            _emit(payload, args.json)
            return 0

        if args.command == "onboard":
            payload = app.onboard(args.brain_answers)
            _emit(payload, args.json)
            return 0

        if args.command == "status":
            payload = app.status()
            _emit(payload, args.json)
            return 1 if payload.get("state") in {"unhealthy", "migration-required", "absent"} else 0

        if args.command == "doctor":
            payload = app.doctor()
            _emit(payload, args.json)
            return 0 if payload.get("ok") else 1

        if args.command == "component":
            payload = app.component_action(args.component, args.action)
            _emit(payload, args.json)
            if args.action == "doctor":
                return 0 if payload.get("ok") else 1
            return 0

        if args.command == "update":
            payload = app.apply_update(args.release_set) if args.apply else app.update_plan(args.release_set)
            _emit(payload, args.json)
            return 0

        if args.command == "rollback":
            payload = app.rollback(args.release_set, apply=args.apply)
            _emit(payload, args.json)
            return 0

        if args.command == "support-bundle":
            path = create_support_bundle(app, args.output)
            payload = {"support_bundle": str(path)}
            _emit(payload, args.json)
            if not args.json:
                print(path)
            return 0

        if args.command == "open":
            _emit(app.open_info(), args.json)
            return 0

        if args.command == "releases":
            payload = [
                {
                    "id": x.id,
                    "profile": x.profile,
                    "status": x.status,
                    "components": [c.id for c in x.components],
                    "blockers": list(x.blockers),
                }
                for x in app.catalog.release_sets()
            ]
            _emit(payload, args.json)
            return 0

        parser.error("unknown command")
        return 2
    except ReleaseBlockedError as exc:
        payload = {"error": exc.code, "message": str(exc), "blockers": exc.blockers}
        _emit(payload, getattr(args, "json", False))
        return 3
    except UnsupportedLifecycle as exc:
        payload = {"error": "OWNER_LIFECYCLE_UNSUPPORTED", "message": str(exc)}
        _emit(payload, getattr(args, "json", False))
        return 4
    except (DistributionError, ProcessError, RuntimeError) as exc:
        code = getattr(exc, "code", "DISTRIBUTION_FAILED")
        payload = {"error": code, "message": str(exc)}
        if isinstance(exc, ProcessError):
            payload["command"] = exc.argv
            payload["returncode"] = exc.returncode
            payload["stdout"] = exc.stdout
            payload["stderr"] = exc.stderr
        _emit(payload, getattr(args, "json", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
