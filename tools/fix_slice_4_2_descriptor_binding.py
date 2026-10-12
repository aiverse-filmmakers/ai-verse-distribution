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
    '''    if descriptor.get("component_id") != component.id:\n        raise InfrastructureEvidenceError(\n            f"{component.id}: component release descriptor owner mismatch"\n        )\n    if descriptor.get("revision") != component.revision:\n        raise InfrastructureEvidenceError(\n            f"{component.id}: component release descriptor revision mismatch"\n        )\n\n\ndef _validate_infrastructure_block(\n''',
    '''    if descriptor.get("component_id") != component.id:\n        raise InfrastructureEvidenceError(\n            f"{component.id}: component release descriptor owner mismatch"\n        )\n\n\ndef _validate_infrastructure_block(\n''',
)

replace_once(
    "src/aiverse_distribution/infrastructure_gate.py",
    '''    if infrastructure.get("contract_version") != INFRASTRUCTURE_CONTRACT:\n''',
    '''    # The carrier is read from the exact target Git snapshot. Historical\n    # component descriptors may have a stale top-level revision field, and that\n    # must not retroactively block already-qualified software updates when no\n    # infrastructure contract is published. Once infrastructure recipes exist,\n    # however, the descriptor and every recipe must bind to this exact target.\n    if descriptor.get("revision") != component.revision:\n        raise InfrastructureEvidenceError(\n            f"{component.id}: infrastructure descriptor revision mismatch"\n        )\n    if infrastructure.get("contract_version") != INFRASTRUCTURE_CONTRACT:\n''',
)

replace_once(
    "tests/test_infrastructure_update_gate.py",
    '''    def test_descriptor_without_infrastructure_is_compatible(self):\n        payload = descriptor()\n        payload["migration"].pop("infrastructure")\n        result = self.evaluate(payload)\n        self.assertEqual(result["state"], "COMPATIBLE")\n        self.assertTrue(result["activation_allowed"])\n        self.assertTrue(result["staging_allowed"])\n\n''',
    '''    def test_descriptor_without_infrastructure_is_compatible(self):\n        payload = descriptor()\n        payload["migration"].pop("infrastructure")\n        result = self.evaluate(payload)\n        self.assertEqual(result["state"], "COMPATIBLE")\n        self.assertTrue(result["activation_allowed"])\n        self.assertTrue(result["staging_allowed"])\n\n    def test_exact_target_snapshot_without_infrastructure_tolerates_legacy_descriptor_revision(self):\n        payload = descriptor()\n        payload["migration"].pop("infrastructure")\n        payload["revision"] = "f" * 40\n        result = self.evaluate(payload)\n        self.assertEqual(result["state"], "COMPATIBLE")\n        self.assertTrue(result["activation_allowed"])\n\n''',
)
