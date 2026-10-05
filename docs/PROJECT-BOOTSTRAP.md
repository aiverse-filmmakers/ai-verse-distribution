# Member project bootstrap

The OS belongs at the project root. This lets the host discover the shipped
`AGENTS.md`, `CLAUDE.md`, `.agents/skills/`, and `.claude/skills/` directly.
Do not copy Distribution source or create its virtual environment in that root
before OS installation: the owner installer requires an empty destination.

Planned layout:

```text
parent/
  Member project/             OS root and member-owned workspace state
  .ai-verse-tools/
    <project-path-hash>/
      project.json           bootstrap ownership and progress receipt
      tools/                 privately managed prerequisite programs
      downloads/             verified download cache
      staging/               disposable installer preparation
      d/                     compact Distribution sources, environments and receipts
```

The private Distribution state directory is intentionally named `d` to preserve
Windows path budget for Git's internal object/pack paths. Bootstrap child Git
processes also enable `core.longpaths=true` through process-scoped Git config on
Windows. This does not modify the member's global Git configuration.

Use `aiverse project-plan --project <folder> --json` to check the layout without
writing any files. A custom `--stack` must be outside the project. Existing
member files are never implicitly adopted or replaced. A nonempty project can
resume only with matching bootstrap and Distribution installation receipts;
the normal owner revision/integrity checks still apply during execution.

Implementation status: layout admission, prerequisite inventory, serialized
tool-stack claims, resumable progress receipts, and checksum-pinned private
Node/npm acquisition are implemented. `aiverse project-tools --project <folder>
--json` checks available tools without writing. Add `--prepare-node` to obtain a
private Node 22/npm 10 bundle if the available pair is incompatible. Neither
command installs Core or modifies the OS destination.

Private Python acquisition is implemented for macOS/Linux arm64 and x64 and
Windows x64. Use `--prepare-python` to obtain the pinned standalone Python
3.11.17 build when no compatible Python is found. It includes SSL, venv, and
package installation support. The POSIX and PowerShell entry scripts under
`scripts/` can prepare a temporary checksum-pinned Python interpreter outside
the project when no compatible Python exists. They pass control to the same
project installer and remove first-stage temporary files afterward.

Distribution Skills commands now honor `AI_VERSE_SKILLS_ROOT`, matching the OS
custom-provider location setting. Complete project-local Skills discovery and
host invocation still require composed acceptance.

`project-init --project <folder> --distribution-source <checkout>` now composes
preparation, private Distribution environment installation, Core owner install,
setup, and status/doctor checks. It preserves an unchanged generated launcher
and adds local extension instructions using the existing OS registry hook.
It does not change tracked OS instructions. The launcher supplies private
Node and Skills paths on future calls, without depending on the source checkout.

Member installation requires an admitted Core release whose evidence contains
`member_bootstrap.status = accepted` and `audit_repairs_included = true`.
No current historical Core manifest has this new gate. The public command
therefore stops before downloads or destination writes. An internal Python
acceptance driver can exercise historical release mechanics with
`qualification=True`; this is not a public CLI bypass or member release.

Git setup uses an existing OS package manager when `--install-system-git` is
explicitly allowed: Homebrew or Apple's Command Line Tools on macOS,
apt/dnf/pacman on Linux, and user-scoped winget on Windows. Git is the exception
to private runtime installation. OS approval or installer completion may be
required. Linux uses noninteractive sudo so the chat never waits for an
invisible password prompt. Unsupported systems stop with an installation link.

Repaired-release admission, actual host/memory invocation acceptance, and hosted
Windows/Linux qualification remain incomplete. Preparation commands do not
constitute release qualification. The project-bootstrap workflow exercises
historical Core mechanics separately from member release admission.

Node archives are pinned to official v22.23.3 checksums. Extraction rejects
outbound paths, outbound links, special entries, and oversized archives. Reuse
compares the installed tree to a fresh extraction of verified cached bytes
before running it. Existing system programs are not replaced. This private
bundle was exercised on macOS arm64 with Node 22.23.3 and npm 10.9.9; Linux and
Windows platform paths still need hosted acceptance.

The repaired Skills source requires Git LFS during provider checkout on this
machine. Candidate metadata explicitly requests it. Setup reuses a suitable
existing helper or obtains a checksum-pinned private Git LFS 3.8.0 binary.
LFS filtering is configured only for project child processes; no global
`git lfs install` or user Git configuration change is performed. Future
launchers reconstruct that process configuration without persisting inherited
Git configuration values or credentials.

Distribution child commands and generated launchers use isolated Python imports,
so a developer checkout's PYTHONPATH cannot shadow the private installed package.

Standalone Python archive URLs and SHA256 digests are pinned from the
`astral-sh/python-build-standalone` release `20261003`, rather than assuming
Python.org publishes relocatable interpreter archives. The macOS arm64 package
passed real version and SSL/venv/ensurepip probes locally. Other platforms still
need hosted acceptance.

Local composed mechanics acceptance on macOS arm64 installed all five historical
Core components at the project root, completed owner setup/status/doctor, and
invoked status through the persistent private launcher with state `ready`.
This proves installation mechanics for that historical set, not inclusion of
later audit fixes or complete Codex/Claude/Cursor behavior.

Required order for the complete entry point:

1. Admit project layout and an exact release set before destination writes.
2. Claim the separate tool stack and serialize bootstrap writers.
3. Reuse compatible prerequisite programs; obtain missing tools privately with
   verified download provenance and platform-specific compatibility checks.
4. Prepare Distribution in staging, retaining a resumable progress receipt.
5. Install Core at the still-empty project root through its owner lifecycles.
6. Complete setup and discover host instructions at the final project location.
7. Run owner health checks plus actual host and memory acceptance.

No moving branch may replace an admitted component revision. The older Core
release remains historical until a release manifest containing the later audit
repairs is qualified and admitted. Green layout tests alone do not qualify it.
