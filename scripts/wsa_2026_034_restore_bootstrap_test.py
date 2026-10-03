from pathlib import Path

path = Path("tests/test_bootstrap.py")
text = path.read_text(encoding="utf-8")

old_import = "import tempfile\nimport unittest\nfrom pathlib import Path\n"
new_import = "import tempfile\nimport unittest\nfrom contextlib import contextmanager\nfrom pathlib import Path\n"
if text.count(old_import) != 1:
    raise SystemExit(f"bootstrap import anchor count = {text.count(old_import)}")
text = text.replace(old_import, new_import, 1)

old_class = '''class FakeState:
    def __init__(self, value=None, home=None):
        self.value = value
        self.writes = []
        self.home = Path(home or tempfile.gettempdir())

    def load(self):
        return self.value

    def venv_dir(self, revision):
        return self.home / "venvs" / "ai-verse-brain" / revision

    def write(self, value, archive_previous=False):
        self.value = value
        self.writes.append((value, archive_previous))


'''
new_class = '''class FakeState:
    def __init__(self, value=None, home=None):
        self.value = value
        self.writes = []
        self.home = Path(home or tempfile.gettempdir())
        self.pending = None
        self.generation = 0 if value is not None else -1

    def load(self):
        if self.value is None:
            return None
        if not self.pending:
            return self.value
        visible = dict(self.value)
        visible["_pending_lifecycle"] = dict(self.pending)
        return visible

    def venv_dir(self, revision):
        return self.home / "venvs" / "ai-verse-brain" / revision

    @contextmanager
    def lifecycle_transaction(self, timeout=30.0):
        del timeout
        yield self

    def begin_effect(self, operation_key, *, metadata=None):
        marker = {
            "token": "fake-effect-token",
            "operation_key": operation_key,
            "base_generation": self.generation,
            "metadata": dict(metadata or {}),
        }
        if self.pending and (
            self.pending["operation_key"] != marker["operation_key"]
            or self.pending["metadata"] != marker["metadata"]
        ):
            raise RuntimeError("fake state already has a different pending lifecycle effect")
        self.pending = marker
        return dict(marker)

    def write(
        self,
        value,
        archive_previous=False,
        *,
        expected_generation=None,
        allow_pending_token=None,
    ):
        del expected_generation, allow_pending_token
        persisted = dict(value)
        persisted.pop("_pending_lifecycle", None)
        self.generation += 1
        persisted["_receipt_generation"] = self.generation
        self.value = persisted
        self.writes.append((persisted, archive_previous))
        return persisted

    def commit_effect(self, value, marker, *, archive_previous=False):
        if not self.pending or self.pending["token"] != marker["token"]:
            raise RuntimeError("fake lifecycle effect ownership changed")
        persisted = self.write(
            value,
            archive_previous=archive_previous,
            expected_generation=marker["base_generation"],
            allow_pending_token=marker["token"],
        )
        self.pending = None
        return persisted


'''
if text.count(old_class) != 1:
    raise SystemExit(f"FakeState anchor count = {text.count(old_class)}")
text = text.replace(old_class, new_class, 1)
path.write_text(text, encoding="utf-8")
