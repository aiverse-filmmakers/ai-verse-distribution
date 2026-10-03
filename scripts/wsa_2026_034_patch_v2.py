from pathlib import Path

patcher = Path("scripts/wsa_2026_034_patch.py")
source = patcher.read_text(encoding="utf-8")
old = '''for method in ("install", "setup", "safe_reconcile", "start", "component_action", "apply_update", "rollback"):
    text = one(
        text,
        f"    def {method}(\\n",
        f"    @_serialized_lifecycle\\n    def {method}(\\n",
        f"decorate {method}",
    )
'''
new = '''for method in ("install", "setup", "start", "component_action", "apply_update"):
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
if source.count(old) != 1:
    raise SystemExit(f"expected one decorator loop, found {source.count(old)}")
source = source.replace(old, new, 1)
exec(compile(source, str(patcher), "exec"))
