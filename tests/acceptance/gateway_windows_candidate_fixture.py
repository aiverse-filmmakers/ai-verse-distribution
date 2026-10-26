"""CI-only compose fixture. Do not publish a new release or alter historical pins."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "src" / "aiverse_distribution" / "catalog"
RELEASE_ID = "agent-gateway-windows-qualification-2026-10-23"
BASE_ID = "agent-public-beta-2026-09-14"
GATEWAY_SHA = "386ff40135a841c27bfd106531b38a7f37c1c227"


def main() -> None:
    release_path = CATALOG / "release_sets.json"
    compatibility_path = CATALOG / "compatibility.json"
    releases = json.loads(release_path.read_text(encoding="utf-8"))
    matrix = json.loads(compatibility_path.read_text(encoding="utf-8"))
    assert RELEASE_ID not in {item["id"] for item in releases["release_sets"]}
    base = next(item for item in releases["release_sets"] if item["id"] == BASE_ID)
    candidate = copy.deepcopy(base)
    candidate["id"] = RELEASE_ID
    candidate["classification"] = "ci-disposable-exact-ref-qualification-only"
    candidate["promotion"] = {"default_channel": False, "automatic_update": False}
    candidate["evidence"] = {"status": "awaiting-composed-qualification", "gateway_revision": GATEWAY_SHA}
    for component in candidate["components"]:
        if component["id"] == "ai-verse-gateway":
            component["revision"] = GATEWAY_SHA
    expected = {component["id"]: component["revision"] for component in candidate["components"]}
    baseline = {component["id"]: component["revision"] for component in base["components"]}
    assert len(expected) == len(baseline) == 9 and expected["ai-verse-gateway"] == GATEWAY_SHA
    # G4.2 qualification may change ONE revision inside the transient candidate.
    # No sibling owner ref, default Agent channel, accepted release, or
    # published promotion may be altered even in the runner's staged catalog.
    assert all(
        expected[name] == original for name, original in baseline.items()
        if name != "ai-verse-gateway"
    )
    assert candidate["promotion"] == {"default_channel": False, "automatic_update": False}
    assert candidate["evidence"]["status"] == "awaiting-composed-qualification"
    channels_before = copy.deepcopy(releases["channels"])
    base_before = copy.deepcopy(base)
    releases["release_sets"].append(candidate)
    compatibility = copy.deepcopy(matrix["release_sets"][BASE_ID])
    compatibility["update_from"] = [RELEASE_ID]
    compatibility["rollback_to"] = [RELEASE_ID]
    matrix["release_sets"][RELEASE_ID] = compatibility
    assert releases["channels"] == channels_before
    assert next(item for item in releases["release_sets"] if item["id"] == BASE_ID) == base_before
    assert matrix["release_sets"][BASE_ID] != compatibility or BASE_ID != RELEASE_ID
    release_path.write_text(json.dumps(releases, indent=2) + "\n", encoding="utf-8")
    compatibility_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as env:
        env.write(f"AI_VERSE_ACCEPTANCE_RELEASE_SET={RELEASE_ID}\n")
        env.write("AI_VERSE_ACCEPTANCE_EXPECTED_REFS=" + json.dumps(expected, separators=(",", ":")) + "\n")
    print("Prepared CI-only exact-source Agent candidate", RELEASE_ID, GATEWAY_SHA)
    print("Default Agent release channel and committed catalogs remain unchanged.")


if __name__ == "__main__":
    main()
