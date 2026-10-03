from pathlib import Path

ORCH = Path("src/aiverse_distribution/orchestrator.py")
CLI = Path("src/aiverse_distribution/cli.py")


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one occurrence, found {count}")
    return text.replace(old, new, 1)


text = ORCH.read_text(encoding="utf-8")
text = one(
    text,
    "import shutil\nimport sys\nfrom importlib import resources\n",
    "import shutil\nimport sys\nfrom functools import wraps\nfrom importlib import resources\n",
    "functools import",
)
text = one(
    text,
    "\n\nclass Orchestrator:\n",
    "\n\ndef _serialized_lifecycle(method):\n"
    "    @wraps(method)\n"
    "    def wrapped(self, *args, **kwargs):\n"
    "        with self.state.lifecycle_transaction():\n"
    "            return method(self, *args, **kwargs)\n\n"
    "    return wrapped\n\n\n"
    "class Orchestrator:\n",
    "lifecycle decorator",
)
for method in ("install", "setup", "safe_reconcile", "start", "component_action", "apply_update", "rollback"):
    text = one(
        text,
        f"    def {method}(\n",
        f"    @_serialized_lifecycle\n    def {method}(\n",
        f"decorate {method}",
    )

text = one(
    text,
    "            receipt = self._install_component(component, root, release)\n"
    "            lock[\"components\"][component.id] = receipt\n"
    "            lock[\"state\"] = \"installing\"\n"
    "            self.state.write(lock, archive_previous=False)\n",
    "            effect = self.state.begin_effect(\n"
    "                f\"install:{release.id}:{component.id}:{component.revision}\",\n"
    "                metadata={\"component\": component.id, \"revision\": component.revision},\n"
    "            )\n"
    "            receipt = self._install_component(component, root, release)\n"
    "            lock[\"components\"][component.id] = receipt\n"
    "            lock[\"state\"] = \"installing\"\n"
    "            lock = self.state.commit_effect(lock, effect, archive_previous=False)\n",
    "install owner effect",
)
text = one(
    text,
    "        lock[\"state\"] = \"installed\"\n"
    "        lock[\"installed_at\"] = now_iso()\n"
    "        self.state.write(lock, archive_previous=False)\n"
    "        return lock\n",
    "        lock[\"state\"] = \"installed\"\n"
    "        lock[\"installed_at\"] = now_iso()\n"
    "        lock = self.state.write(lock, archive_previous=False)\n"
    "        return lock\n",
    "install final receipt",
)
text = one(
    text,
    "            commands = owner_setup(\n"
    "                cid,\n"
    "                root=root,\n"
    "                source=source,\n"
    "                revision=component.revision,\n"
    "                state=self.state,\n"
    "            )\n"
    "            results[cid] = [_safe_result(x) for x in commands]\n"
    "            lock[\"components\"][cid][\"setup_completed_at\"] = now_iso()\n"
    "            lock[\"components\"][cid][\"last_setup_result\"] = \"success\"\n"
    "            self.state.write(lock, archive_previous=False)\n",
    "            effect = self.state.begin_effect(\n"
    "                f\"setup:{release.id}:{cid}:{component.revision}\",\n"
    "                metadata={\"component\": cid, \"revision\": component.revision},\n"
    "            )\n"
    "            commands = owner_setup(\n"
    "                cid,\n"
    "                root=root,\n"
    "                source=source,\n"
    "                revision=component.revision,\n"
    "                state=self.state,\n"
    "            )\n"
    "            results[cid] = [_safe_result(x) for x in commands]\n"
    "            lock[\"components\"][cid][\"setup_completed_at\"] = now_iso()\n"
    "            lock[\"components\"][cid][\"last_setup_result\"] = \"success\"\n"
    "            lock = self.state.commit_effect(lock, effect, archive_previous=False)\n",
    "setup owner effect",
)
text = one(
    text,
    "            for workspace_id in selected_workspaces:\n"
    "                request = {\n",
    "            for workspace_id in selected_workspaces:\n"
    "                effect = self.state.begin_effect(\n"
    "                    f\"setup-workspace:{release.id}:{workspace_id}\",\n"
    "                    metadata={\"workspace\": workspace_id},\n"
    "                )\n"
    "                request = {\n",
    "workspace effect begin",
)
text = one(
    text,
    "                workspace_results.append({\"workspace\": workspace_id, \"response\": response})\n"
    "            results[\"ai-verse-data-workspaces\"] = workspace_results\n",
    "                workspace_results.append({\"workspace\": workspace_id, \"response\": response})\n"
    "                lock = self.state.commit_effect(lock, effect, archive_previous=False)\n"
    "            results[\"ai-verse-data-workspaces\"] = workspace_results\n",
    "workspace effect commit",
)
text = one(
    text,
    "            if host_adapter.is_file():\n"
    "                target = root / \".aiverse\" / \"brain-host.json\"\n"
    "                result = run([\n",
    "            if host_adapter.is_file():\n"
    "                target = root / \".aiverse\" / \"brain-host.json\"\n"
    "                effect = self.state.begin_effect(\n"
    "                    f\"setup-system-host:{release.id}\",\n"
    "                    metadata={\"target\": str(target)},\n"
    "                )\n"
    "                result = run([\n",
    "system host effect begin",
)
text = one(
    text,
    "                results[\"system-host\"] = [_safe_result(result)]\n\n"
    "            lock = self.state.load() or lock\n",
    "                results[\"system-host\"] = [_safe_result(result)]\n"
    "                lock = self.state.commit_effect(lock, effect, archive_previous=False)\n\n"
    "            lock = self.state.load() or lock\n",
    "system host effect commit",
)
text = one(
    text,
    "        apply_result = run(\n"
    "            [\n"
    "                \"node\",\n",
    "        effect = self.state.begin_effect(\n"
    "            f\"safe-reconcile:{lock['release_set_id']}:brain-attachment\",\n"
    "            metadata={\"component\": \"ai-verse-brain\"},\n"
    "        )\n"
    "        apply_result = run(\n"
    "            [\n"
    "                \"node\",\n",
    "safe reconcile effect begin",
)
text = one(
    text,
    "        if failed or unexpected_executed or len(executed) > 1:\n"
    "            return {\n"
    "                \"state\": \"failed\",\n"
    "                \"safe\": True,\n"
    "                \"reason\": \"owner-controlled reconcile did not complete cleanly\",\n"
    "                \"mutated\": bool(applied.get(\"mutated\")),\n"
    "                \"result\": sanitize(applied),\n"
    "            }\n\n"
    "        return {\n",
    "        if failed or unexpected_executed or len(executed) > 1:\n"
    "            return {\n"
    "                \"state\": \"failed\",\n"
    "                \"safe\": True,\n"
    "                \"reason\": \"owner-controlled reconcile did not complete cleanly\",\n"
    "                \"mutated\": bool(applied.get(\"mutated\")),\n"
    "                \"result\": sanitize(applied),\n"
    "            }\n\n"
    "        lock = self.state.load() or lock\n"
    "        lock = self.state.commit_effect(lock, effect, archive_previous=False)\n"
    "        return {\n",
    "safe reconcile effect commit",
)
text = one(
    text,
    "            previous = lock.get(\"components\", {}).get(component_id)\n"
    "            receipt = self._install_component(component, root, release)\n"
    "            if previous and not previous.get(\"uninstalled_at\"):\n"
    "                receipt[\"setup_completed_at\"] = previous.get(\"setup_completed_at\")\n"
    "                if previous.get(\"last_setup_result\"):\n"
    "                    receipt[\"last_setup_result\"] = previous[\"last_setup_result\"]\n"
    "            lock[\"components\"][component_id] = receipt\n"
    "            self.state.write(lock, archive_previous=False)\n"
    "            return {\"component\": component_id, \"action\": action, \"changed\": True}\n",
    "            previous = lock.get(\"components\", {}).get(component_id)\n"
    "            effect = self.state.begin_effect(\n"
    "                f\"component:install:{component_id}:{component.revision}\",\n"
    "                metadata={\"component\": component_id, \"revision\": component.revision},\n"
    "            )\n"
    "            receipt = self._install_component(component, root, release)\n"
    "            if previous and not previous.get(\"uninstalled_at\"):\n"
    "                receipt[\"setup_completed_at\"] = previous.get(\"setup_completed_at\")\n"
    "                if previous.get(\"last_setup_result\"):\n"
    "                    receipt[\"last_setup_result\"] = previous[\"last_setup_result\"]\n"
    "            lock[\"components\"][component_id] = receipt\n"
    "            lock = self.state.commit_effect(lock, effect, archive_previous=False)\n"
    "            return {\"component\": component_id, \"action\": action, \"changed\": True}\n",
    "component install effect",
)
text = one(
    text,
    "        lock, release, component, root, source = self._context(component_id)\n"
    "        if action in {\"enable\", \"disable\"}:\n"
    "            result = owner_enablement(\n"
    "                component_id, action, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "        elif action == \"uninstall\":\n"
    "            result = owner_uninstall(\n"
    "                component_id, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "            lock[\"components\"][component_id][\"uninstalled_at\"] = now_iso()\n"
    "            self.state.write(lock, archive_previous=False)\n"
    "        elif action == \"update\":\n"
    "            result = owner_update(\n"
    "                component_id, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "            if result is None:\n"
    "                return {\"component\": component_id, \"action\": action, \"changed\": False, \"note\": \"already pinned\"}\n"
    "        else:\n"
    "            raise DistributionError(f\"unknown component action: {action}\")\n"
    "        return {\"component\": component_id, \"action\": action, \"result\": _safe_result(result)}\n",
    "        lock, release, component, root, source = self._context(component_id)\n"
    "        effect = self.state.begin_effect(\n"
    "            f\"component:{action}:{component_id}:{component.revision}\",\n"
    "            metadata={\"component\": component_id, \"revision\": component.revision, \"action\": action},\n"
    "        )\n"
    "        if action in {\"enable\", \"disable\"}:\n"
    "            result = owner_enablement(\n"
    "                component_id, action, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "        elif action == \"uninstall\":\n"
    "            result = owner_uninstall(\n"
    "                component_id, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "            lock[\"components\"][component_id][\"uninstalled_at\"] = now_iso()\n"
    "        elif action == \"update\":\n"
    "            result = owner_update(\n"
    "                component_id, root=root, source=source, revision=component.revision, state=self.state\n"
    "            )\n"
    "        else:\n"
    "            raise DistributionError(f\"unknown component action: {action}\")\n"
    "        lock = self.state.commit_effect(lock, effect, archive_previous=False)\n"
    "        if action == \"update\" and result is None:\n"
    "            return {\"component\": component_id, \"action\": action, \"changed\": False, \"note\": \"already pinned\"}\n"
    "        return {\"component\": component_id, \"action\": action, \"result\": _safe_result(result)}\n",
    "component mutating effects",
)
text = one(
    text,
    "            if os_changed and new_os:\n",
    "            effect = self.state.begin_effect(\n"
    "                f\"release-transition:{transition_kind}:{lock['release_set_id']}:{target.id}\",\n"
    "                metadata={\"from\": lock[\"release_set_id\"], \"to\": target.id, \"kind\": transition_kind},\n"
    "            )\n\n"
    "            if os_changed and new_os:\n",
    "release transition effect begin",
)
text = one(
    text,
    "            self.state.write(new_lock, archive_previous=True)\n"
    "            return {**plan, \"applied\": True, \"changed\": True}\n",
    "            new_lock = self.state.commit_effect(new_lock, effect, archive_previous=True)\n"
    "            return {**plan, \"applied\": True, \"changed\": True}\n",
    "release transition effect commit",
)
text = one(
    text,
    "    def status(self, component_id: Optional[str] = None) -> Dict[str, Any]:\n"
    "        lock = self.state.load()\n"
    "        if not lock:\n"
    "            return {\"state\": \"absent\", \"components\": {}}\n",
    "    def status(self, component_id: Optional[str] = None) -> Dict[str, Any]:\n"
    "        lock = self.state.load()\n"
    "        if not lock:\n"
    "            return {\"state\": \"absent\", \"components\": {}}\n"
    "        pending = lock.get(\"_pending_lifecycle\")\n"
    "        if pending:\n"
    "            return {\n"
    "                \"state\": \"recovery-required\",\n"
    "                \"release_set_id\": lock.get(\"release_set_id\"),\n"
    "                \"profile\": lock.get(\"profile\"),\n"
    "                \"root\": lock.get(\"root\"),\n"
    "                \"components\": {},\n"
    "                \"recovery\": {\n"
    "                    \"operation_key\": pending.get(\"operation_key\"),\n"
    "                    \"started_at\": pending.get(\"started_at\"),\n"
    "                },\n"
    "            }\n",
    "status pending recovery",
)
text = one(
    text,
    "    def doctor(self, component_id: Optional[str] = None) -> Dict[str, Any]:\n"
    "        lock = self.state.load()\n"
    "        if not lock:\n"
    "            return {\"ok\": False, \"state\": \"absent\", \"depth\": [\"structural\"]}\n",
    "    def doctor(self, component_id: Optional[str] = None) -> Dict[str, Any]:\n"
    "        lock = self.state.load()\n"
    "        if not lock:\n"
    "            return {\"ok\": False, \"state\": \"absent\", \"depth\": [\"structural\"]}\n"
    "        pending = lock.get(\"_pending_lifecycle\")\n"
    "        if pending:\n"
    "            return {\n"
    "                \"ok\": False,\n"
    "                \"state\": \"recovery-required\",\n"
    "                \"release_set_id\": lock.get(\"release_set_id\"),\n"
    "                \"root\": lock.get(\"root\"),\n"
    "                \"depth\": [\"structural\", \"lifecycle-recovery\"],\n"
    "                \"components\": {},\n"
    "                \"recovery\": {\n"
    "                    \"operation_key\": pending.get(\"operation_key\"),\n"
    "                    \"started_at\": pending.get(\"started_at\"),\n"
    "                },\n"
    "            }\n",
    "doctor pending recovery",
)
ORCH.write_text(text, encoding="utf-8")

cli = CLI.read_text(encoding="utf-8")
cli = one(
    cli,
    "return 1 if payload.get(\"state\") in {\"unhealthy\", \"migration-required\", \"absent\"} else 0",
    "return 1 if payload.get(\"state\") in {\"unhealthy\", \"migration-required\", \"recovery-required\", \"absent\"} else 0",
    "CLI top-level status recovery exit",
)
cli = one(
    cli,
    "return 1 if payload.get(\"state\") in {\"unhealthy\", \"migration-required\", \"absent\"} else 0",
    "return 1 if payload.get(\"state\") in {\"unhealthy\", \"migration-required\", \"recovery-required\", \"absent\"} else 0",
    "CLI component status recovery exit",
)
CLI.write_text(cli, encoding="utf-8")
