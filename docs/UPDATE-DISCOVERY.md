# Installed Core update discovery

The installed project-bound `aiverse update` command checks the official Distribution repository's main ref once, freezes its exact commit, and verifies a private immutable source snapshot. The catalog, companion locks, transition rules and updater come from that same snapshot. Core selection and transition authority remain the existing released catalog and qualification contracts; a Git branch is never a component revision.

## Trust and compatibility

The repository is fixed in Distribution code, not supplied by member content or a receipt. Git supplies the official commit/tree; critical source bytes are checked against that tree, including files marked assume-unchanged. Unknown import files, symlinks, altered bytes, wrong origin/commit, invalid project binding or unsupported handoff/dependency requirements stop execution. This protects lifecycle provenance; it is not protection against an adversary controlling the user's Git installation, Python interpreter or filesystem concurrently.

`pyproject.toml` declares protocol 1 and the local entrypoint. Only the dependency-free Python >=3.11 interface is currently supported. Unsupported requirements need the canonical bootstrap rather than a guessed pip command. The initially admitted legacy protocol uses `main`; implementations with discovery use `_local_main` to prevent recursive refresh.

## Selection and recovery

Snapshots live under the receipt-bound private Distribution home at `updater/<commit>`. `updater/active.json` selects verified local tooling; it is installation metadata, not another release catalog. Selection uses the existing lifecycle kernel lock and atomic JSON writer. The candidate must recognize the actual installed full Core component identity under that lock, including changes made by another lifecycle command.

Selection precedes Core mutation so local doctor/restore can read new receipts after an interruption. Once tooling is prepared, the existing canonical updater performs all transition, owner, preservation, LKG and health work. A Core conflict can leave the newly verified tooling selected, without claiming that Core updated. Existing snapshots and the original installed transport remain available. Preparation failures preserve the previous selection; interrupted unselected staging is disposable. No running environment is overwritten and no new service runs in the background.

Local status/doctor/recovery use the selected verified snapshot without checking the network. Corrupt cached tooling fails for review rather than silently falling back to an engine that may not recognize current state; canonical bootstrap remains the support recovery path.

## Preview and offline behavior

`aiverse update --plan` may acquire and verify a snapshot, but does not activate it or modify member state/installation receipts. Default apply always verifies the live official ref; network failure reports unknown latest status and does not use a cached no-op as proof of being current. Advanced explicit `--to` requests use the selected local catalog and existing exact-transition checks.

## Existing installations

A historical updater cannot gain discovery code without an initial tooling refresh. Follow INSTALL.md's repeated-bootstrap route from a current official checkout once. This updates private Distribution tooling and invokes the same Core lifecycle. No root reset, member data migration or component-by-component pull is involved. New installations receive the transport directly.

## Qualification

`tests/acceptance/update_discovery_acceptance.py` installs a genuine older admitted Core with its historical updater, demonstrates its old catalog no-op, then equips a disposable transport fixture with that same old catalog. The public installed default update must discover the newer admitted Core, preserve synthetic member files, keep preview read-only, pass final doctor, repeat as a no-op and retain offline local health. This is a stale-catalog simulation using real admitted releases, not a fabricated production release. The Installed update discovery workflow runs it on Linux, macOS and Windows. Focused tests cover provenance, unsupported protocol, paths, interruption, concurrency and failure propagation.
