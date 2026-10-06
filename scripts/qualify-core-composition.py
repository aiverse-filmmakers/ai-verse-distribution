"""Freeze repaired owner inputs; do not admit or promote a member release."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
REFS = {
    "OS": "e74a4e05b1f891e6f871f34a298bf10363a11d88",
    "Brain": "7c77b053df627e61b3d7f11d029500ab61095c9c",
    "Memory": "b0cae8cd8da38aa657fbc736c575177aa75e5ec7",
    "Skills": "afde5c06307fba7d074de2929c2eb6c3dc6bdab8",
    "Data": "6e8781ff1dcd96a35dfb27868bd60605361483d0",
}


def git(repository, *args):
    return subprocess.run(["git", "-C", str(repository), *args], capture_output=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracker", type=Path, required=True)
    parser.add_argument("--owner-parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tracker = args.tracker.read_text(encoding="utf-8")
    merges = {name: set() for name in REFS}
    for section in re.split(r"\n## ", tracker):
        owner = re.search(r"^\*\*Owner:\*\*[ \t]*AI-Verse-(OS|Brain|Memory|Skills|Data)[ \t]*$", section, re.MULTILINE)
        if owner:
            merges[owner[1]].update(re.findall(r"\*\*Merged (?:owner|" + owner[1] + r") (?:ref|commit):\*\*\s*`([0-9a-f]{40})`", section))
        for name in REFS:
            merges[name].update(re.findall(r"\*\*Merged " + name + r":\*\*\s*`([0-9a-f]{40})`", section))
    components = []
    ancestry = {}
    for order, (name, revision) in enumerate(REFS.items(), 1):
        repository = args.owner_parent / f"ai-verse-{name.lower()}-audit"
        if not merges[name]:
            raise RuntimeError(f"No recorded repair merge found for {name}; do not infer audit inclusion")
        for merged in sorted(merges[name]):
            git(repository, "merge-base", "--is-ancestor", merged, revision)
        ancestry[name] = {"revision": revision, "tree": git(repository, "rev-parse", revision + "^{tree}").decode().strip(),
                          "recorded_repair_merges_present": sorted(merges[name])}
        components.append({"id": "ai-verse-" + name.lower(), "repository": f"https://github.com/aiverse-filmmakers/AI-Verse-{name}.git",
                           "revision": revision, "install_order": order * 10})

    revision = REFS["Data"]
    package_bytes = git(args.owner_parent / "ai-verse-data-audit", "show", revision + ":package.json")
    package = json.loads(package_bytes)
    old = SOURCE / "src/aiverse_distribution/dependency_locks/ai-verse-data/8edde7dca5afa34e300130cc6b8ee2b4170ad40f"
    lock = json.loads((old / "package-lock.json").read_bytes())
    manifest = json.loads((old / "lock.json").read_bytes())
    root = lock["packages"][""]
    for key in ("name", "dependencies", "devDependencies"):
        if root.get(key) != package.get(key):
            raise RuntimeError(f"Data {key} changed; resolve and qualify a new dependency graph")
    lock["version"] = root["version"] = package["version"]
    lock_bytes = (json.dumps(lock, indent=2) + "\n").encode()
    manifest.update({"source_revision": revision, "source_manifest_sha256": hashlib.sha256(package_bytes).hexdigest(),
                     "lockfile_sha256": hashlib.sha256(lock_bytes).hexdigest()})
    manifest["provenance"]["reason"] = "Exact repaired Data source retains the pinned dependency graph; bind its companion to the changed package version and exact source manifest. Qualification remains pending."
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    lock_path = args.output / "dependency_locks/ai-verse-data" / revision
    lock_path.mkdir(parents=True, exist_ok=True)
    (lock_path / "package-lock.json").write_bytes(lock_bytes)
    (lock_path / "lock.json").write_bytes(manifest_bytes)
    components[-1]["dependency_lock"] = {"scheme": manifest["scheme"], "manifest": f"ai-verse-data/{revision}/lock.json",
                                          "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}
    candidate = {"schema_version": 1, "id": "core-member-bootstrap-candidate-2026-10-05", "profile": "core", "status": "blocked",
                 "created_at": "2026-10-05", "blockers": ["Exact composition and member bootstrap qualification pending"],
                 "runtime_requirements": {"git_lfs": True},
                 "components": components, "authority": {"grants_permissions": False, "transfers_brain_strategy": False, "initializes_all_workspaces": False},
                 "evidence": {"audit_ancestry": ancestry,
                    "tracker_sha256": hashlib.sha256(args.tracker.read_bytes()).hexdigest(),
                    "member_bootstrap": {"status": "pending", "audit_repairs_included": False}}}
    (args.output / "candidate.json").write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: len(merges[name]) for name in REFS}))


if __name__ == "__main__":
    main()
