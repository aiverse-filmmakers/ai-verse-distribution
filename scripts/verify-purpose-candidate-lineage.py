#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "qualification" / "purpose-context" / "candidate.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(argv)} failed with {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    payload = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    evidence = payload.get("evidence", {})
    checks = evidence.get("lineage_checks", {})
    components = {item["id"]: item for item in payload.get("components", [])}

    if payload.get("lineage", {}).get("policy") != "same-or-descendant":
        raise RuntimeError("candidate lineage policy is not same-or-descendant")
    if set(checks) != set(components):
        raise RuntimeError("lineage checks do not cover exactly the frozen candidate components")

    for component_id, component in components.items():
        revision = component.get("revision", "")
        check = checks[component_id]
        baseline = check.get("baseline", "")
        recorded_candidate = check.get("candidate", "")
        repository = component.get("repository", "")
        if not SHA40.fullmatch(revision) or not SHA40.fullmatch(baseline):
            raise RuntimeError(f"{component_id}: candidate/baseline is not an exact commit SHA")
        if recorded_candidate != revision:
            raise RuntimeError(f"{component_id}: recorded lineage candidate does not equal frozen revision")
        if check.get("behind_by") != 0:
            raise RuntimeError(f"{component_id}: recorded lineage is behind repaired baseline")
        if baseline == revision:
            print(f"{component_id}: identical to repaired baseline")
            continue

        with tempfile.TemporaryDirectory(prefix=f"purpose-lineage-{component_id}-") as tmp:
            repo = Path(tmp) / "repo"
            run(["git", "init", "-q", str(repo)])
            run(["git", "-C", str(repo), "remote", "add", "origin", repository])
            run(["git", "-C", str(repo), "fetch", "--quiet", "--no-tags", "--filter=blob:none", "origin", baseline, revision])
            result = subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", baseline, revision],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"{component_id}: frozen candidate {revision} is not a descendant of repaired baseline {baseline}\n"
                    f"stderr:\n{result.stderr}"
                )
            print(f"{component_id}: same-or-descendant PASS ({baseline} -> {revision})")

    print("Purpose Context candidate exact-ref lineage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
