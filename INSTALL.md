# Install, Update, Upgrade, or Restore AI-Verse in a Project

This is the canonical project lifecycle procedure for coding agents such as Codex and Claude Code.

## User-facing contract

A member with a fresh project should only need to say something equivalent to:

> Clone this locally and use its install procedure to set AI-Verse up in this project.

A member with AI-Verse already installed can use plain requests such as:

> Update AI-Verse.

> Check AI-Verse.

> See if AI-Verse needs any setup upgrades.

> Restore AI-Verse to the last safe point.

The member does not need to know release IDs, component revisions, repository paths, infrastructure generations, migration recipes, prerequisite versions, or recovery internals.

## Fresh install

1. Identify the user's intended AI-Verse project folder from the current/opened project context. Ask only if the target is genuinely ambiguous.
2. Use this Distribution repository as the installer source. Keep installer/tool state wherever the canonical bootstrap requires; do not burden the user with that implementation detail.
3. Run the platform entrypoint against the target project:

macOS/Linux:

```bash
./scripts/bootstrap.sh --project "<target-project>"
```

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1 --project "<target-project>"
```

4. Do not manually select a Core release or manually clone OS, Brain, Memory, Skills, or Data. Distribution resolves the current admitted Core and exact immutable component revisions automatically.
5. Let the bootstrap prepare/reuse required tools, install the Core, run owner-controlled setup, create the persistent project launcher/instructions, and execute final `status` and `doctor` checks.
6. Treat the installation as successful only when the bootstrap exits successfully and its final health checks pass.
7. After success, continue work from the installed project root. Read the installed `AGENTS.md` and `AI-VERSE.yaml`; Claude Code also reads `CLAUDE.md`. Use the generated runtime capability adapters from there.
8. First-use onboarding is progressive and conversational. Start with the user's real task. Ask for deeper profile/preferences/goals only when relevant or when the user explicitly asks for full onboarding.

## Existing installation lifecycle

Do not delete, reclone, reset, or reinstall an existing AI-Verse project as a normal lifecycle operation.

### Software update

If the member asks to update AI-Verse, use:

```text
aiverse update
```

This applies only an explicitly admitted software transition. It preserves user-owned/ambiguous local state, creates the required recovery protection before mutation, executes owner-controlled migration/reconcile where admitted, and finishes with health verification.

For a non-mutating preview:

```text
aiverse update --plan
```

Normal update does not silently apply optional structural convergence.

### Whole-install health

If the member asks whether AI-Verse is healthy or what needs attention, use:

```text
aiverse doctor
```

This is the whole-install aggregate surface. Distribution invokes owner-backed health checks internally and returns one combined truth. Component-scoped diagnostics remain an expert/internal compatibility surface.

### Structural upgrade

If the member asks to improve/converge the installed AI-Verse structure, preview first:

```text
aiverse upgrade
```

This is read-only. It classifies owner-published structural work as safe/no-op, optional, required, or blocked/review according to the admitted contracts.

Apply only after explicit mutation intent:

```text
aiverse upgrade --apply
```

Do not invent a structural migration when an owner publishes no admitted recipe. Unsupported Workspace relocation remains blocked/review rather than being normalized automatically.

### Last-Known-Good restore

If the member asks to recover the whole supported local installation, preview first:

```text
aiverse restore
```

Preview must not change the retained recovery target or project state.

Apply only after explicit restore intent:

```text
aiverse restore --apply
```

Restore reproduces the declared covered state and exact software reconstruction represented by the verified Last-Known-Good point. Credential-shaped/external state and other explicit exclusions are not falsely rewound.

### Repeated bootstrap

If the member repeats the normal bootstrap/install procedure against a completed Core installation, the bootstrap detects the existing verified project receipt, refreshes only the private Distribution tool from the installer checkout, and routes the project to the preservation-safe lifecycle updater instead of a destructive reinstall path.

## Coding-agent routing rules

- Route whole-install software selection/update, aggregate doctor, structural upgrade orchestration, Last-Known-Good protection, and restore through Distribution.
- Do not bypass Distribution by manually editing receipts, release sets, recovery manifests, or owner state.
- Do not duplicate owner lifecycle logic. OS, Brain, Memory, Skills, Data and later profile components remain authoritative for their own component contracts.
- If ownership, local modifications, migration, health, or recovery state is ambiguous, stop and report the conflict. Do not fall back to delete/reinstall guidance.
- Exact release IDs and component refs are advanced/support evidence, not ordinary member inputs.
- Keep the member-facing response concise and plain English. Internal paths, generation IDs, migration operations and compatibility evidence may be shown only when useful for diagnosis.

## Safety behavior

The lifecycle procedure intentionally refuses to overwrite unrelated existing project files, silently adopt an incompatible installation, invent unsupported structural migration, bypass stale-plan checks, or continue after failed final health verification.

Internal release integrity, exact component refs, prerequisite isolation, setup ordering, migration ownership, transaction checkpoints, Last-Known-Good rotation, restore coverage and health verification are responsibilities of Distribution and the component owners, not of the member prompt.

Canonical lifecycle ownership and qualification evidence are summarized in `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md`.
