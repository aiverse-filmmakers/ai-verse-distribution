from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEY = re.compile(
    r"(secret|token|password|credential|authorization|cookie)",
    re.I,
)
_SENSITIVE_TEXT = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
]


def sanitize_text(value: str) -> str:
    redacted = value
    redacted = _SENSITIVE_TEXT[0].sub("Bearer <redacted>", redacted)
    redacted = _SENSITIVE_TEXT[1].sub(
        lambda match: f"{match.group(1)}=<redacted>",
        redacted,
    )
    return redacted


def sanitize(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {k: sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value
