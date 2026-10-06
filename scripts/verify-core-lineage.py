#!/usr/bin/env python3
"""Enforce the append-only Core lineage and protected-component ancestry."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINEAGE_PATH = Path("src/aiverse_distribution/catalog/core_lineage.json")


def run(argv: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def load_head() -> dict:
    return json.loads((ROOT / LINEAGE_PATH).read_text(encoding="utf-8"))


def load_base(ref: str, head: dict) -> dict | None:
    result = run(["git", "show", f"{ref}:{LINEAGE_PATH.as_posix()}"], cwd=ROOT, check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def release_map(document: dict) -> dict[str, dict]:
    releases = document.get("release_sets", [])
    if not isinstance(releases, list):
        raise RuntimeError("core-lineage release_sets must be a list")
    result: dict[str, dict] = {}
    for raw in releases:
        rid = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(rid, str) or not rid or rid in result:
            raise RuntimeError("core-lineage release ids must be unique non-empty strings")
        result[rid] = raw
    return result


def catalog_anchor_release(release_id: str) -> dict:
    catalog = json.loads(
        (ROOT / "src/aiverse_distribution/catalog/release_sets.json").read_text(encoding="utf-8")
    )
    for raw in catalog.get("release_sets", []):
        if raw.get("id") == release_id:
            return raw
    raise RuntimeError(f"legacy Core anchor is missing from release_sets.json: {release_id}")


def parent_release(document: dict, releases: dict[str, dict], child: dict) -> dict:
    parent_id = child.get("lineage", {}).get("parent")
    if not isinstance(parent_id, str) or not parent_id:
        raise RuntimeError(f"{child.get('id')}: missing lineage parent")
    if parent_id in releases:
        return releases[parent_id]
    if parent_id == document.get("anchor_release"):
        return catalog_anchor_release(parent_id)
    raise RuntimeError(f"{child.get('id')}: lineage parent {parent_id} is not in the ledger or anchor")


def prove_repository_ancestry(repository: str, parent: str, child: str) -> None:
    if parent == child:
        return
    with tempfile.TemporaryDirectory(prefix="aiverse-core-lineage-") as folder:
        repo = Path(folder) / "repo"
        cloned = run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", repository, str(repo)],
            check=False,
        )
        if cloned.returncode != 0:
            raise RuntimeError(f"could not clone {repository}: {cloned.stderr.strip()}")
        for revision in (parent, child):
            exists = run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=repo, check=False)
            if exists.returncode != 0:
                fetched = run(
                    ["git", "fetch", "--quiet", "--filter=blob:none", "origin", revision],
                    cwd=repo,
                    check=False,
                )
                if fetched.returncode != 0:
                    raise RuntimeError(
                        f"{repository}: cannot fetch protected Core revision {revision}: "
                        f"{fetched.stderr.strip()}"
                    )
        ancestry = run(["git", "merge-base", "--is-ancestor", parent, child], cwd=repo, check=False)
        if ancestry.returncode != 0:
            raise RuntimeError(
                f"{repository}: Core regression blocked; {child} is not the same as or a descendant of {parent}"
            )


def validate_append_only(head: dict, base: dict | None) -> None:
    head_releases = release_map(head)
    current = head.get("current_release")
    anchor = head.get("anchor_release")
    protected = head.get("protected_components")
    if not isinstance(current, str) or current not in head_releases:
        raise RuntimeError("current_release must name a release in the forward Core ledger")
    if not isinstance(anchor, str) or not anchor:
        raise RuntimeError("anchor_release is required")
    if not isinstance(protected, list) or not protected or len(set(protected)) != len(protected):
        raise RuntimeError("protected_components must be a unique non-empty list")

    if base is None:
        first = head_releases[current]
        if first.get("lineage", {}).get("parent") != anchor:
            raise RuntimeError("initial Core ledger release must descend directly from the legacy anchor")
    else:
        for key in ("schema_version", "policy", "anchor_release", "protected_components"):
            if head.get(key) != base.get(key):
                raise RuntimeError(f"Core lineage policy field is immutable: {key}")
        base_releases = release_map(base)
        for rid, raw in base_releases.items():
            if head_releases.get(rid) != raw:
                raise RuntimeError(f"published Core lineage entry is immutable: {rid}")
        old_current = base.get("current_release")
        if current != old_current:
            if head_releases[current].get("lineage", {}).get("parent") != old_current:
                raise RuntimeError(
                    f"new current Core must directly descend from previous current Core {old_current}"
                )

    ancestry_checks = []
    for rid, child in head_releases.items():
        if child.get("lineage", {}).get("policy") != "same-or-descendant":
            raise RuntimeError(f"{rid}: unsupported Core lineage policy")
        parent = parent_release(head, head_releases, child)
        child_components = {item["id"]: item for item in child.get("components", [])}
        parent_components = {item["id"]: item for item in parent.get("components", [])}
        for component_id in protected:
            if component_id not in child_components or component_id not in parent_components:
                raise RuntimeError(f"{rid}: protected Core component disappeared: {component_id}")
            child_component = child_components[component_id]
            parent_component = parent_components[component_id]
            if child_component["repository"] != parent_component["repository"]:
                raise RuntimeError(f"{rid}: protected Core repository changed: {component_id}")
            prove_repository_ancestry(
                child_component["repository"],
                parent_component["revision"],
                child_component["revision"],
            )
            ancestry_checks.append(
                {
                    "release": rid,
                    "component": component_id,
                    "parent": parent_component["revision"],
                    "child": child_component["revision"],
                }
            )

    print(
        json.dumps(
            {
                "ok": True,
                "current_release": current,
                "anchor_release": anchor,
                "protected_components": protected,
                "ancestry_checks": ancestry_checks,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    args = parser.parse_args()
    head = load_head()
    base = load_base(args.base_ref, head)
    validate_append_only(head, base)


if __name__ == "__main__":
    main()
