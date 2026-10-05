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
      distribution-state/    Distribution sources, environments and receipts
```

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
package installation support. This code still requires a Python interpreter to
start; the entry path for a machine with no Python remains to be implemented.

Distribution Skills commands now honor `AI_VERSE_SKILLS_ROOT`, matching the OS
custom-provider location setting. Complete project-local Skills discovery and
host invocation still require composed acceptance.

Git acquisition, launchers, and the complete installation entry point are not
yet implemented. These preparation
commands do not constitute release qualification.

Node archives are pinned to official v22.23.3 checksums. Extraction rejects
outbound paths, outbound links, special entries, and oversized archives. Reuse
compares the installed tree to a fresh extraction of verified cached bytes
before running it. Existing system programs are not replaced. This private
bundle was exercised on macOS arm64 with Node 22.23.3 and npm 10.9.9; Linux and
Windows platform paths still need hosted acceptance.

Standalone Python archive URLs and SHA256 digests are pinned from the
`astral-sh/python-build-standalone` release `20261003`, rather than assuming
Python.org publishes relocatable interpreter archives. The macOS arm64 package
passed real version and SSL/venv/ensurepip probes locally. Other platforms still
need hosted acceptance.

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
