from pathlib import Path

path = Path("src/aiverse_distribution/orchestrator.py")
text = path.read_text(encoding="utf-8")


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one occurrence, found {count}")
    text = text.replace(old, new, 1)


one(
    "from .state import StateStore, now_iso\n",
    "from .state import LifecycleRecoveryRequired, StateStore, now_iso\n",
    "state recovery import",
)
one(
    "        release = self.catalog.get_release(lock[\"release_set_id\"], require_released=True)\n"
    "        wanted = [component_id] if component_id else self._profile_component_ids(lock, release)\n",
    "        release = self.catalog.get_release(lock[\"release_set_id\"], require_released=True)\n"
    "        wanted = [component_id] if component_id else self._profile_component_ids(lock, release)\n"
    "        pending_operation = (lock.get(\"_pending_lifecycle\") or {}).get(\"operation_key\")\n"
    "        recovery_waiting = bool(pending_operation)\n\n"
    "        def should_run_recovery_step(operation_key: str) -> bool:\n"
    "            nonlocal recovery_waiting\n"
    "            if not recovery_waiting:\n"
    "                return True\n"
    "            if operation_key == pending_operation:\n"
    "                recovery_waiting = False\n"
    "                return True\n"
    "            return False\n",
    "setup recovery cursor",
)
one(
    "        for cid in wanted:\n"
    "            lock, _, component, root, source = self._context(cid)\n"
    "            effect = self.state.begin_effect(\n"
    "                f\"setup:{release.id}:{cid}:{component.revision}\",\n"
    "                metadata={\"component\": cid, \"revision\": component.revision},\n"
    "            )\n",
    "        for cid in wanted:\n"
    "            lock, _, component, root, source = self._context(cid)\n"
    "            operation_key = f\"setup:{release.id}:{cid}:{component.revision}\"\n"
    "            if not should_run_recovery_step(operation_key):\n"
    "                continue\n"
    "            effect = self.state.begin_effect(\n"
    "                operation_key,\n"
    "                metadata={\"component\": cid, \"revision\": component.revision},\n"
    "            )\n",
    "setup component recovery",
)
one(
    "            for workspace_id in selected_workspaces:\n"
    "                effect = self.state.begin_effect(\n"
    "                    f\"setup-workspace:{release.id}:{workspace_id}\",\n"
    "                    metadata={\"workspace\": workspace_id},\n"
    "                )\n",
    "            for workspace_id in selected_workspaces:\n"
    "                operation_key = f\"setup-workspace:{release.id}:{workspace_id}\"\n"
    "                if not should_run_recovery_step(operation_key):\n"
    "                    continue\n"
    "                effect = self.state.begin_effect(\n"
    "                    operation_key,\n"
    "                    metadata={\"workspace\": workspace_id},\n"
    "                )\n",
    "setup workspace recovery",
)
one(
    "            if host_adapter.is_file():\n"
    "                target = root / \".aiverse\" / \"brain-host.json\"\n"
    "                effect = self.state.begin_effect(\n"
    "                    f\"setup-system-host:{release.id}\",\n"
    "                    metadata={\"target\": str(target)},\n"
    "                )\n"
    "                result = run([\n"
    "                    sys.executable,\n"
    "                    str(host_adapter),\n"
    "                    \"--root\",\n"
    "                    str(root),\n"
    "                    \"--write-config\",\n"
    "                    str(target),\n"
    "                ])\n"
    "                results[\"system-host\"] = [_safe_result(result)]\n"
    "                lock = self.state.commit_effect(lock, effect, archive_previous=False)\n",
    "            if host_adapter.is_file():\n"
    "                target = root / \".aiverse\" / \"brain-host.json\"\n"
    "                operation_key = f\"setup-system-host:{release.id}\"\n"
    "                if should_run_recovery_step(operation_key):\n"
    "                    effect = self.state.begin_effect(\n"
    "                        operation_key,\n"
    "                        metadata={\"target\": str(target)},\n"
    "                    )\n"
    "                    result = run([\n"
    "                        sys.executable,\n"
    "                        str(host_adapter),\n"
    "                        \"--root\",\n"
    "                        str(root),\n"
    "                        \"--write-config\",\n"
    "                        str(target),\n"
    "                    ])\n"
    "                    results[\"system-host\"] = [_safe_result(result)]\n"
    "                    lock = self.state.commit_effect(lock, effect, archive_previous=False)\n",
    "setup host recovery",
)
one(
    "            lock[\"state\"] = \"setup\"\n"
    "            lock[\"setup_completed_at\"] = now_iso()\n"
    "            self.state.write(lock, archive_previous=False)\n\n"
    "        return {\"release_set_id\": release.id, \"root\": str(root), \"results\": results}\n",
    "            lock[\"state\"] = \"setup\"\n"
    "            lock[\"setup_completed_at\"] = now_iso()\n"
    "            self.state.write(lock, archive_previous=False)\n\n"
    "        if recovery_waiting:\n"
    "            raise LifecycleRecoveryRequired(\n"
    "                f\"pending lifecycle operation {pending_operation!r} is not part of this setup retry\"\n"
    "            )\n"
    "        return {\"release_set_id\": release.id, \"root\": str(root), \"results\": results}\n",
    "setup unmatched recovery",
)
one(
    "        lock, release, component, root, source = self._context(component_id)\n"
    "        effect = self.state.begin_effect(\n",
    "        if action not in {\"enable\", \"disable\", \"uninstall\", \"update\"}:\n"
    "            raise DistributionError(f\"unknown component action: {action}\")\n\n"
    "        lock, release, component, root, source = self._context(component_id)\n"
    "        effect = self.state.begin_effect(\n",
    "component action validation",
)

path.write_text(text, encoding="utf-8")
