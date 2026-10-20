# Updating installations with local source edits

Normal `aiverse update` still selects the admitted Core channel and keeps custom source by default. Its project-private updater now offers bounded preparation under the OS-owned `ai-verse-os/local-source-adoption-v1` contract. No agent should manually reset or stash files after an update refusal.

`aiverse update --plan` reports local source actions and genuine conflicts. `aiverse update --plan --local-source official` previews retiring eligible software edits. After the member chooses official code, `aiverse update --local-source official` saves exact originals privately and performs the normal update. An ordinary update can automatically recognize source changes already included in the admitted target. Choosing official source does not authorize overwriting arbitrary personal files, unknown adapters or staged work.

Preparation preserves additive privacy ignore rules in project-local Git exclusions. It can relocate append-only additions from the starter knowledge index into ignored `knowledge/local-customizations.md`, preserving the exact local routes. Arbitrary knowledge rewrites require review. Other user/owner data, extensions and hook trust are outside this operation.

An incoming release file already present as an untracked local file is admitted only when exact content and platform-representable mode match. Its original is captured and verified privately, then that single file is temporarily parked so normal Git activation can proceed. Failure restores it; success supplies the same file through the official release. Different files, unsafe objects and directories are never cleaned recursively.

The preparation and Core journals share the existing lifecycle lock. Exact source originals and modes are captured before any write; preparation intent is durable before every write. A customized-source capture is not called a healthy Last-Known-Good release. Old-source qualification and final aggregate health still run. Recovery restores the original local edits after a failed/rolled-back update; it stops rather than overwriting later member edits or making up an owner-data downgrade. After success, originals remain recoverable in private `source-adoptions` archives and are not silently re-applied to official code.

The packaged contract is bound to an exact OS repository revision and canonical digest in `catalog/local_source_adoption.json`. It never trusts a member-edited local policy file for mutation authority. Publication of this feature does not change admitted Core release pins.

## Older project launchers

The canonical repeated-bootstrap route refreshes only private Distribution tooling, then refreshes the receipt-owned generated launcher and hands off to `aiverse update`. `aiverse project-refresh --project <existing-project>` exposes that bounded launcher refresh for tooling maintenance. It refuses unknown or locally edited launchers. It changes no member OS source or user content; it is not a reinstall. The new launcher reaches the whole-install entrypoint and exposes its private executable directory to owner subprocesses.

## Qualification

Unit checks cover classified source, privacy additions/refusals, live knowledge routes, untracked target collisions, staged edits, symlinks, plan drift, interrupted preparation, concurrent-edit refusal, recovery after activation and launcher refresh. The populated acceptance driver supports `AI_VERSE_ACCEPTANCE_LOCAL_SOURCE=1`: it constructs the fourteen-file legacy scenario and nine target-identical incoming-file collisions, updates through the canonical command, and checks exact preservation plus the explicitly admitted knowledge relocation. The release workflow runs it on Linux, macOS and Windows in a separate temporary fixture.
