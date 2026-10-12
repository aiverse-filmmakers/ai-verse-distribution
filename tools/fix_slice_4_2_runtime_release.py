from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one patch anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/aiverse_distribution/infrastructure_gate.py",
    '''        # Unit/legacy fixture ReleaseSets without canonical raw release metadata are\n        # outside runtime admission. Keep existing isolated tests scoped to the\n        # behavior they exercise rather than causing network descriptor probes.\n        if not target.raw:\n            return {\n''',
    '''        # Unit/legacy fixture ReleaseSets without canonical catalog-shaped raw\n        # metadata are outside runtime admission. `raw` is also used by some\n        # preservation tests to carry generated-file fixtures, so non-empty alone\n        # cannot prove this is an admitted runtime release.\n        runtime_release = (\n            isinstance(target.raw, dict)\n            and target.raw.get("id") == target.id\n            and target.raw.get("profile") == target.profile\n            and isinstance(target.raw.get("components"), list)\n        )\n        if not runtime_release:\n            return {\n''',
)

replace_once(
    "tests/test_infrastructure_update_gate.py",
    '''    def test_non_runtime_fixture_release_keeps_existing_unit_scope(self):\n        reader = Mock(side_effect=AssertionError("fixture must not fetch network metadata"))\n        gate = InfrastructureUpdateGate(descriptor_reader=reader)\n        result = gate.evaluate(target=release(raw=False), changed_components={"ai-verse-example"})\n        self.assertEqual(result["state"], "COMPATIBLE")\n        reader.assert_not_called()\n\n''',
    '''    def test_non_runtime_fixture_release_keeps_existing_unit_scope(self):\n        reader = Mock(side_effect=AssertionError("fixture must not fetch network metadata"))\n        gate = InfrastructureUpdateGate(descriptor_reader=reader)\n        result = gate.evaluate(target=release(raw=False), changed_components={"ai-verse-example"})\n        self.assertEqual(result["state"], "COMPATIBLE")\n        reader.assert_not_called()\n\n    def test_non_catalog_raw_fixture_metadata_does_not_trigger_descriptor_network_probe(self):\n        fixture_target = ReleaseSet(\n            id="core-target",\n            profile="core",\n            status="released",\n            components=release().components,\n            blockers=(),\n            raw={"distribution_generated_files": [{"path": "run.py"}]},\n        )\n        reader = Mock(side_effect=AssertionError("fixture metadata must not fetch descriptors"))\n        gate = InfrastructureUpdateGate(descriptor_reader=reader)\n        result = gate.evaluate(\n            target=fixture_target,\n            changed_components={"ai-verse-example"},\n        )\n        self.assertEqual(result["state"], "COMPATIBLE")\n        reader.assert_not_called()\n\n''',
)
