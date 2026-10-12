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


def patch_core_update() -> None:
    replace_once(
        "src/aiverse_distribution/core_update.py",
        "from .generated_refresh import (\n    apply_generated_refresh,\n    plan_generated_refresh,\n    restore_generated_refresh,\n)\n",
        "from .generated_refresh import (\n    apply_generated_refresh,\n    plan_generated_refresh,\n    restore_generated_refresh,\n)\nfrom .infrastructure_gate import InfrastructureUpdateGate, require_update_activation\n",
    )
    replace_once(
        "src/aiverse_distribution/core_update.py",
        "        transition_contract: Optional[CoreTransitionContract] = None,\n    ) -> None:\n        super().__init__(state=state, catalog=catalog)\n        self.transition_contract = transition_contract or CoreTransitionContract(self.catalog)\n        self.update_journal = CoreUpdateJournal(self.state.home)\n",
        "        transition_contract: Optional[CoreTransitionContract] = None,\n        infrastructure_gate: Optional[InfrastructureUpdateGate] = None,\n    ) -> None:\n        super().__init__(state=state, catalog=catalog)\n        self.transition_contract = transition_contract or CoreTransitionContract(self.catalog)\n        self.update_journal = CoreUpdateJournal(self.state.home)\n        self.infrastructure_gate = infrastructure_gate or InfrastructureUpdateGate()\n",
    )
    replace_once(
        "src/aiverse_distribution/core_update.py",
        "            \"brain_handover\": False,\n            \"permission_grants\": False,\n        }\n        if not changes:\n            plan[\"message\"] = \"AI-Verse is already current.\"\n        return plan\n",
        "            \"brain_handover\": False,\n            \"permission_grants\": False,\n        }\n        if transition_kind == \"update\":\n            infrastructure = self.infrastructure_gate.evaluate(\n                target=target,\n                changed_components=plan[\"changed_components\"],\n            )\n            plan[\"infrastructure\"] = infrastructure\n            plan[\"activation_allowed\"] = infrastructure.get(\"activation_allowed\") is True\n        else:\n            plan[\"activation_allowed\"] = True\n        if not changes:\n            plan[\"message\"] = \"AI-Verse is already current.\"\n        return plan\n",
    )
    replace_once(
        "src/aiverse_distribution/core_update.py",
        "                \"message\": \"AI-Verse is already current.\",\n            }\n\n        lock = self.state.load()\n",
        "                \"message\": \"AI-Verse is already current.\",\n            }\n\n        if transition_kind == \"update\":\n            require_update_activation(plan)\n\n        lock = self.state.load()\n",
    )


def patch_recovery_orchestrator() -> None:
    replace_once(
        "src/aiverse_distribution/recovery_orchestrator.py",
        "from .core_update_health import require_final_health\n",
        "from .core_update_health import require_final_health\nfrom .infrastructure_gate import require_update_activation\n",
    )
    replace_once(
        "src/aiverse_distribution/recovery_orchestrator.py",
        "                if recovery:\n                    result[\"recovery\"] = recovery\n                return result\n\n            lkg = self.ensure_last_known_good()\n",
        "                if recovery:\n                    result[\"recovery\"] = recovery\n                return result\n\n            if transition_kind == \"update\":\n                require_update_activation(plan)\n\n            lkg = self.ensure_last_known_good()\n",
    )


def patch_update_output() -> None:
    replace_once(
        "src/aiverse_distribution/update_output.py",
        "    if \"applied\" not in payload:\n        lines = [\"AI-Verse update plan\", \"\", \"Core\", f\"{source_text} -> {target_text}\"]\n        if payload.get(\"noop\") or not components:\n            lines.extend([\"\", \"AI-Verse is already up to date.\"])\n        else:\n            lines.extend([\"\", \"Would update:\"])\n            lines.extend(f\"- {component}\" for component in components)\n        return \"\\n\".join(lines)\n",
        "    if \"applied\" not in payload:\n        lines = [\"AI-Verse update plan\", \"\", \"Core\", f\"{source_text} -> {target_text}\"]\n        if payload.get(\"noop\") or not components:\n            lines.extend([\"\", \"AI-Verse is already up to date.\"])\n        else:\n            lines.extend([\"\", \"Would update:\"])\n            lines.extend(f\"- {component}\" for component in components)\n\n        infrastructure = payload.get(\"infrastructure\")\n        if isinstance(infrastructure, dict):\n            state = infrastructure.get(\"state\")\n            if state == \"OPTIONAL\":\n                lines.extend([\n                    \"\",\n                    \"Setup improvement: available separately\",\n                    \"This software update can continue and will not rearrange your setup.\",\n                ])\n            elif state == \"REQUIRED\":\n                lines.extend([\n                    \"\",\n                    \"Setup change required\",\n                    \"AI-Verse found a setup change that must be completed before the new version can finish.\",\n                    \"Nothing has been changed yet.\",\n                    \"Action: complete the setup upgrade before updating.\",\n                ])\n            elif state == \"BLOCKED/REVIEW\":\n                lines.extend([\n                    \"\",\n                    \"Setup review required\",\n                    \"AI-Verse cannot safely confirm the setup changes needed for this version.\",\n                    \"Nothing has been changed.\",\n                ])\n        return \"\\n\".join(lines)\n",
    )
    replace_once(
        "src/aiverse_distribution/update_output.py",
        "    if isinstance(health, dict) and health.get(\"ok\") is True:\n        lines.extend([\"\", \"Health checks: PASS\"])\n    lines.append(\"AI-Verse is up to date.\")\n",
        "    if isinstance(health, dict) and health.get(\"ok\") is True:\n        lines.extend([\"\", \"Health checks: PASS\"])\n    infrastructure = payload.get(\"infrastructure\")\n    if isinstance(infrastructure, dict) and infrastructure.get(\"state\") == \"OPTIONAL\":\n        lines.extend([\n            \"\",\n            \"Setup improvement remains available separately.\",\n            \"This update did not rearrange your setup.\",\n        ])\n    lines.append(\"AI-Verse is up to date.\")\n",
    )


if __name__ == "__main__":
    patch_core_update()
    patch_recovery_orchestrator()
    patch_update_output()
