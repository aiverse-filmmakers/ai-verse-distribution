from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


class PreservationMismatch(RuntimeError):
    """Raised when state required to survive a Core update changed unexpectedly."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def fingerprint_tree(root: Path, paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Return a deterministic content fingerprint for selected member-owned paths.

    Directories are expanded recursively. Symlinks are fingerprinted as links rather
    than followed, so an update cannot hide a replacement behind path resolution.
    Missing paths are represented explicitly.
    """

    root = Path(root).expanduser().resolve()
    result: dict[str, dict[str, Any]] = {}
    for item in sorted({Path(value) for value in paths}, key=lambda value: value.as_posix()):
        target = root / item
        key = item.as_posix()
        if target.is_symlink():
            result[key] = {"type": "symlink", "target": str(target.readlink())}
            continue
        if not target.exists():
            result[key] = {"type": "missing"}
            continue
        if target.is_file():
            data = target.read_bytes()
            result[key] = {
                "type": "file",
                "size": len(data),
                "sha256": _sha256_bytes(data),
            }
            continue
        if not target.is_dir():
            result[key] = {"type": "other"}
            continue
        result[key] = {"type": "directory"}
        for child in sorted(target.rglob("*"), key=lambda value: value.as_posix()):
            relative = _relative(root, child)
            if child.is_symlink():
                result[relative] = {"type": "symlink", "target": str(child.readlink())}
            elif child.is_dir():
                result[relative] = {"type": "directory"}
            elif child.is_file():
                data = child.read_bytes()
                result[relative] = {
                    "type": "file",
                    "size": len(data),
                    "sha256": _sha256_bytes(data),
                }
            else:
                result[relative] = {"type": "other"}
    return dict(sorted(result.items()))


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def snapshot_sqlite_records(path: Path) -> dict[str, Any]:
    """Snapshot user-visible SQLite table contents independent of DB file layout.

    This intentionally ignores SQLite internal tables and physical byte layout so an
    owner may perform an admitted schema migration while preservation tests still
    prove member records survived unchanged.
    """

    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            if isinstance(row[0], str)
        ]
        snapshot: dict[str, Any] = {}
        for table in tables:
            quoted = _quote_identifier(table)
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({quoted})")
                if isinstance(row[1], str)
            ]
            rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            normalized_rows = [list(row) for row in rows]
            normalized_rows.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
            snapshot[table] = {"columns": columns, "rows": normalized_rows}
        return snapshot
    finally:
        connection.close()


def preserved_sqlite_rows(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Return True when every pre-update table row remains present after migration.

    Extra migration tables/columns are allowed. Existing member row values for the
    columns that existed before the update must remain exactly equal.
    """

    for table, old in before.items():
        new = after.get(table)
        if not isinstance(old, dict) or not isinstance(new, dict):
            return False
        old_columns = list(old.get("columns", []))
        new_columns = list(new.get("columns", []))
        if any(column not in new_columns for column in old_columns):
            return False
        positions = [new_columns.index(column) for column in old_columns]
        projected = [[row[index] for index in positions] for row in new.get("rows", [])]
        projected.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
        expected = [list(row) for row in old.get("rows", [])]
        expected.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
        if projected != expected:
            return False
    return True


def require_preserved(before: Any, after: Any, *, label: str) -> None:
    if before != after:
        raise PreservationMismatch(f"Core update preservation mismatch: {label}")


def require_sqlite_records_preserved(
    before: dict[str, Any], after: dict[str, Any], *, label: str
) -> None:
    if not preserved_sqlite_rows(before, after):
        raise PreservationMismatch(f"Core update SQLite preservation mismatch: {label}")
