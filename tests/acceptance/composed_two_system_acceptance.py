from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="aiverse-two-system-"))
    script = Path(__file__).with_name("agent_acceptance.py")
    specs = (("system-a", 18787, 18788), ("system-b", 18797, 18798))
    processes = []
    for name, gateway_port, bots_port in specs:
        root = base / name
        env = os.environ.copy()
        env.update({
            "AIVERSE_ACCEPTANCE_ROOT": str(root),
            "AIVERSE_GATEWAY_PORT": str(gateway_port),
            "AIVERSE_BOTS_PORT": str(bots_port),
            "AIVERSE_GATEWAY_TOKEN": f"{name}-gateway-token",
            "HOME": str(root / "home"),
            "USERPROFILE": str(root / "home"),
        })
        processes.append((name, root, subprocess.Popen(
            [sys.executable, str(script)], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )))

    failures = []
    for name, root, process in processes:
        output, _ = process.communicate(timeout=1200)
        if process.returncode != 0:
            failures.append(f"{name}: {output[-4000:]}")
        if not (root / "AI-Verse-agent").is_dir():
            failures.append(f"{name}: isolated Agent root missing")
        if not (root / "distribution-agent").is_dir():
            failures.append(f"{name}: isolated Distribution home missing")
    if failures:
        raise RuntimeError("two-system isolation acceptance failed:\n" + "\n".join(failures))
    print('{"two_systems": true, "separate_roots": true, "separate_distribution_homes": true, "simultaneous": true}')


if __name__ == "__main__":
    main()
