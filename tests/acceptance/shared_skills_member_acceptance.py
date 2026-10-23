"""Exercise new member Skills through the installed public owner commands."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run_json(argv, payload=None):
    result = subprocess.run([str(v) for v in argv], input=None if payload is None else json.dumps(payload),
                            text=True, capture_output=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"member Skills acceptance command failed ({result.returncode}): {result.stderr}")
    return json.loads(result.stdout)


def verify_member_library(root: Path, *, fresh: bool):
    config = run_json(["node", root / "scripts/capability-configuration-cli.mjs", "--root", root], {"operation": "read"})
    if not config.get("configured"):
        raise RuntimeError("public lifecycle did not establish provider configuration")
    managed, personal = Path(config["skillsRoot"]), Path(config["localSkillsRoot"])
    if fresh and personal != managed.parent / "member-skills":
        raise RuntimeError("fresh installation did not use its private sibling member library")
    entrypoint = Path(config["skillsEntrypoint"])
    owner = [sys.executable, entrypoint, "--root", managed, "library", "--library-root", personal]
    cli = ["node", root / "scripts/capability-resolver-cli.mjs", "--root", root]
    beta = root / "workspaces/shared-skills-acceptance"
    beta.mkdir(parents=True)
    (beta / "WORKSPACE.yaml").write_text('schema_version: "2.0"\nid: shared-skills-acceptance\nstatus: active\n', encoding="utf-8")
    source = root / "workspaces/alpha/inbox/shared-skills-acceptance"
    source.mkdir(parents=True)
    skill = source / "SKILL.md"
    skill.write_text('---\nname: acceptance-portable-method\ndescription: Verify explicit portable member inputs and results\n---\nUse the declared inputs and verify the output.\n', encoding="utf-8")
    original = hashlib.sha256(skill.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="aiverse-member-import-") as temp:
        admission = Path(temp) / "admission.json"
        admission.write_text(json.dumps({"reusable":True,"contains_workspace_data":False,"contains_credentials":False,"has_workspace_dependencies":False}), encoding="utf-8")
        command = [*owner,"import","--source",source,"--source-scope","workspace:alpha","--visibility","shared","--admission-json",admission]
        plan = run_json(command)
        plan_path = Path(temp) / "plan.json";plan_path.write_text(json.dumps(plan), encoding="utf-8")
        applied = run_json([*command,"--apply-plan",plan_path])
        identity = applied["qualified_id"]
        replay = run_json([*command,"--apply-plan",plan_path])
        if replay["qualified_id"] != identity:
            raise RuntimeError("replayed member import changed identity")
    if hashlib.sha256(skill.read_bytes()).hexdigest() != original:
        raise RuntimeError("member import altered its source")
    for scope in ["workspace:alpha","workspace:shared-skills-acceptance"]:
        selected = run_json(cli,{"operation":"select","scope":scope,"qualified_id":identity})
        if selected.get("status") != "selected":
            raise RuntimeError(f"shared package unavailable in {scope}: {selected}")
    scope="workspace:shared-skills-acceptance"
    planned=run_json(cli,{"operation":"plan-binding","scope":scope,"qualified_id":identity,"alias":"acceptance-portable-method","binding":{"inputs":{"locale":"acceptance"}}})
    run_json(cli,{"operation":"apply-binding","scope":scope,"plan":planned})
    selected=run_json(cli,{"operation":"select","scope":scope,"query":"acceptance-portable-method"})
    if selected.get("status") != "selected" or selected["selection"]["id"] != identity:
        raise RuntimeError("scoped preference did not retain member identity")
    run_json([*owner,"doctor"])
    return {"configured":True,"fresh_private_root":fresh,"cross_workspace_import":True,"source_preserved":True,"retry_identity_preserved":True,"scoped_binding":True}
