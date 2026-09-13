from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


class ProcessError(RuntimeError):
    def __init__(self, argv: Sequence[str], code: int, stdout: str, stderr: str):
        self.argv = list(argv)
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr
        detail = (stderr or stdout).strip()
        super().__init__(f"command failed ({code}): {' '.join(argv)}{': ' + detail if detail else ''}")


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    def as_dict(self) -> dict:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def run(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    check: bool = True,
) -> CommandResult:
    if not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
        raise ValueError("commands must be non-empty argv string arrays")
    merged = os.environ.copy()
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd else None,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    result = CommandResult(list(argv), completed.returncode, completed.stdout, completed.stderr)
    if check and completed.returncode != 0:
        raise ProcessError(result.argv, result.returncode, result.stdout, result.stderr)
    return result


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def version_line(command: str) -> Optional[str]:
    path = which(command)
    if not path:
        return None
    result = run([path, "--version"], check=False)
    if result.returncode != 0:
        return None
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else "available"
