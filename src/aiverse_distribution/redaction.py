from __future__ import annotations

import json
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
    if not isinstance(value, str):
        value = str(value)
    try:
        structured = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        structured = None
    if isinstance(structured, (dict, list)):
        return json.dumps(sanitize(structured), sort_keys=True)

    redacted = value
    redacted = _SENSITIVE_TEXT[0].sub("Bearer <redacted>", redacted)
    redacted = _SENSITIVE_TEXT[1].sub(
        lambda match: f"{match.group(1)}=<redacted>",
        redacted,
    )
    return redacted


_SENSITIVE_ARGUMENT = re.compile(
    r"(secret|token|password|credential|authorization|cookie|api[_-]?key|access[_-]?key)",
    re.I,
)


def sanitize_argv(argv: Any) -> Any:
    if not isinstance(argv, (list, tuple)):
        return sanitize(argv)
    result = []
    redact_next = False
    for item in argv:
        text = str(item)
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        option, separator, argument = text.partition("=")
        if separator and _SENSITIVE_ARGUMENT.search(option):
            result.append(option + "=" + ("<redacted>" if argument else ""))
            continue
        result.append(sanitize_text(text))
        if text.startswith("-") and _SENSITIVE_ARGUMENT.search(text) and not separator:
            redact_next = True
    return result


def sanitize(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {k: sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        if key.lower() in {"argv", "command"}:
            return sanitize_argv(value)
        return [sanitize(v) for v in value]
    if isinstance(value, tuple):
        if key.lower() in {"argv", "command"}:
            return sanitize_argv(value)
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value
