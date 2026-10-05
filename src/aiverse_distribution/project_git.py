"""Explicit system Git setup using documented OS package managers."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from .process import run
from .project_tools import version
from .release_catalog import DistributionError


def git_install_plan() -> dict:
    system = platform.system()
    if system == "Darwin":
        brew = shutil.which("brew")
        if brew:
            return {"commands": [[brew, "install", "git"]], "message": "Install Git using the existing Homebrew installation.", "async": False}
        xcode = shutil.which("xcode-select")
        if xcode:
            return {"commands": [[xcode, "--install"]], "message": "Apple will open its Command Line Tools installer. Complete that window, then retry AI-Verse setup.", "async": True}
    elif system == "Windows":
        winget = shutil.which("winget")
        if winget:
            return {"commands": [[winget, "install", "--id", "Git.Git", "--exact", "--source", "winget", "--scope", "user", "--accept-source-agreements", "--accept-package-agreements"]],
                    "message": "Install Git for the current user with Windows Package Manager.", "async": False}
    elif system == "Linux":
        for manager, arguments in (("apt-get", ["install", "--yes", "git"]), ("dnf", ["install", "--assumeyes", "git"]), ("pacman", ["-S", "--needed", "--noconfirm", "git"])):
            path = shutil.which(manager)
            if path:
                prefix = []
                if os.geteuid() != 0:
                    sudo = shutil.which("sudo")
                    if not sudo:
                        break
                    # Never block a chat installer waiting for an invisible password prompt.
                    prefix = [sudo, "-n"]
                commands = []
                if manager == "apt-get":
                    commands.append([*prefix, path, "update"])
                commands.append([*prefix, path, *arguments])
                return {"commands": commands, "message": "Install Git with the existing Linux package manager; administrator authorization may be required.", "async": False}
    raise DistributionError("No supported Git installer is available. Install Git using https://git-scm.com/install/ and retry; the OS project has not been changed.")


def install_git() -> dict:
    plan = git_install_plan()
    for command in plan["commands"]:
        result = run(command, check=False)
        if result.returncode:
            raise DistributionError(plan["message"] + " The system installer did not complete; retry after resolving its approval or package-manager requirement.")
    if plan["async"]:
        raise DistributionError(plan["message"])
    candidates = [shutil.which("git")]
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
            if base:
                candidates.extend([str(Path(base) / "Programs/Git/cmd/git.exe"), str(Path(base) / "Git/cmd/git.exe")])
    for candidate in candidates:
        if candidate and version(candidate):
            return {"path": candidate, "version": list(version(candidate)), "system_install": True}
    raise DistributionError("Git installation completed but Git is not discoverable yet. Restart the project chat environment and retry setup.")
