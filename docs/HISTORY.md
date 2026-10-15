# Distribution History

## Pre-current-project repository

`aiverse-filmmakers/ai-verse-distribution` existed before the current modular AI-Verse system as a different AI-VERSE profile/package publication experiment.

That work is intentionally preserved in Git history.

Examples visible before the 2026-09-13 reset include release commits such as:

- `f8b430eb933d780dbbdf8ff1c907fe9a7e0fc479`
- `d17041a1fd32e2a0e319ffb265f32750fd4ca05b`
- `72ab178eb0e54f3003205203e36ef188ebb8b139`
- `749c99335e1d9d0273b9d9496263dc08465d644e`

The current-project reset commit is:

`90b9bea24c6ac1082056b605bf01314490395278`

That reset deliberately made the repository small again and redefined it as the canonical one-product Distribution owner.

## Preservation rule

Historical profile/package material is evidence, not current runtime truth.

Do not restore old files into the active tree merely because they once existed.

If a historical idea is reused, it must be re-admitted against:

- the current System ownership law;
- the current install/setup contract;
- immutable release-set rules;
- current component lifecycle;
- current security and authority boundaries;
- current acceptance tests.

## Current role

From 2026-09-13 onward, the active repository purpose is:

```text
one product CLI
+ profiles
+ exact compatible release sets
+ lifecycle orchestration
+ update/rollback selection
+ diagnostics
+ acceptance gates
```

It is not a component-engine monorepo and not a replacement for the historical source repositories.

## 2026-10-12 to 2026-10-15: Safe Infrastructure lifecycle

The Safe Infrastructure Upgrade, Convergence and Recovery program expanded the existing Distribution lifecycle without moving component ownership into Distribution.

The final whole-install contract now separates:

```text
software update
structural upgrade
whole-install doctor
Last-Known-Good recovery
whole-install restore
```

Key outcomes:

- `aiverse update` remains the normal mutating software-update route and `aiverse update --plan` remains its read-only preview;
- normal software update does not silently perform optional structural convergence;
- `aiverse doctor` provides one aggregate whole-install truth while owner checks remain authoritative underneath it;
- `aiverse upgrade` previews owner-published structural state and `aiverse upgrade --apply` is the explicit structural mutation path;
- every mutating admitted update/upgrade is protected by one rotating verification-first whole-install Last-Known-Good recovery point;
- `aiverse restore` previews that retained point and `aiverse restore --apply` explicitly restores declared covered state;
- recovery coverage is explicit through CAPTURE / RECONSTRUCT / REBUILD / EXTERNAL-EXCLUDED classes rather than a blind whole-folder copy promise;
- unsupported historical nested Workspace layouts remain blocked/review and are not automatically relocated;
- the OS owner supplies the explicit Workspace-to-personal capability promotion transaction, including qualified identity change, compatibility repair and idempotent replay;
- supported runtime adapters converge on one Distribution lifecycle instead of creating separate update/doctor/restore implementations;
- permanent `Safe Infrastructure Regression` and `Safe Infrastructure Convergence` workflows now qualify the protected lifecycle across the supported matrix.

The program also exercised a real older admitted Core installation through a real admitted update, compared the result with a fresh install of the same current release, ran the frozen OS capability-promotion contract against the upgraded installation, and restored the retained pre-update recovery point.

The canonical handoff is `docs/SAFE-INFRASTRUCTURE-LIFECYCLE.md`.

This lifecycle completion does not mean all Distribution roadmap work is complete. Full-profile work and separately owned acceptance defects remain governed by their own evidence and release gates.
