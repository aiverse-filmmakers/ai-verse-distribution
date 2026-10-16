from pathlib import Path

path = Path("src/aiverse_distribution/core_promotion.py")
text = path.read_text(encoding="utf-8")

old = '''def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:\n    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")\n'''
new = old + '''\n\ndef _pretty_json_bytes(payload: Mapping[str, Any]) -> bytes:\n    """Return deterministic persisted JSON bytes on every platform."""\n    return (json.dumps(payload, indent=2) + "\\n").encode("utf-8")\n'''
if text.count(old) != 1:
    raise SystemExit("canonical helper anchor mismatch")
text = text.replace(old, new, 1)

old = '''    temporary.write_text(json.dumps(payload, indent=2) + "\\n", encoding="utf-8")\n    os.replace(temporary, path)\n'''
new = '''    temporary.write_bytes(_pretty_json_bytes(payload))\n    os.replace(temporary, path)\n'''
if text.count(old) != 1:
    raise SystemExit("atomic writer anchor mismatch")
text = text.replace(old, new, 1)

old = '''        with os.fdopen(fd, "w", encoding="utf-8") as handle:\n            handle.write(json.dumps(payload, indent=2) + "\\n")\n            handle.flush()\n            os.fsync(handle.fileno())\n'''
new = '''        with os.fdopen(fd, "wb") as handle:\n            handle.write(_pretty_json_bytes(payload))\n            handle.flush()\n            os.fsync(handle.fileno())\n'''
if text.count(old) != 1:
    raise SystemExit("immutable writer anchor mismatch")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
