from pathlib import Path

patcher = Path("scripts/wsa_2026_034_patch.py")
source = patcher.read_text(encoding="utf-8")

old_loop = '''for method in ("install", "setup", "safe_reconcile", "start", "component_action", "apply_update", "rollback"):
    text = one(
        text,
        f"    def {method}(\\n",
        f"    @_serialized_lifecycle\\n    def {method}(\\n",
        f"decorate {method}",
    )
'''
new_loop = '''for method in ("install", "setup", "start", "component_action", "apply_update"):
    text = one(
        text,
        f"    def {method}(\\n",
        f"    @_serialized_lifecycle\\n    def {method}(\\n",
        f"decorate {method}",
    )
text = one(
    text,
    "    def safe_reconcile(self) -> Dict[str, Any]:\\n",
    "    @_serialized_lifecycle\\n    def safe_reconcile(self) -> Dict[str, Any]:\\n",
    "decorate safe_reconcile",
)
text = one(
    text,
    "    def rollback(self, release_set_id: str, apply: bool = False) -> Dict[str, Any]:\\n",
    "    @_serialized_lifecycle\\n    def rollback(self, release_set_id: str, apply: bool = False) -> Dict[str, Any]:\\n",
    "decorate rollback",
)
'''
if source.count(old_loop) != 1:
    raise SystemExit(f"expected one decorator loop, found {source.count(old_loop)}")
source = source.replace(old_loop, new_loop, 1)

old_cli = '''cli = one(
    cli,
    "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"absent\\"} else 0",
    "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"recovery-required\\", \\"absent\\"} else 0",
    "CLI top-level status recovery exit",
)
cli = one(
    cli,
    "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"absent\\"} else 0",
    "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"recovery-required\\", \\"absent\\"} else 0",
    "CLI component status recovery exit",
)
'''
new_cli = '''old_status_exit = "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"absent\\"} else 0"
new_status_exit = "return 1 if payload.get(\\"state\\") in {\\"unhealthy\\", \\"migration-required\\", \\"recovery-required\\", \\"absent\\"} else 0"
if cli.count(old_status_exit) != 2:
    raise SystemExit(f"CLI recovery exits: expected exactly two occurrences, found {cli.count(old_status_exit)}")
cli = cli.replace(old_status_exit, new_status_exit)
'''
if source.count(old_cli) != 1:
    raise SystemExit(f"expected one CLI patch block, found {source.count(old_cli)}")
source = source.replace(old_cli, new_cli, 1)

exec(compile(source, str(patcher), "exec"))
