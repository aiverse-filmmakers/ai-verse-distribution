# Distribution Component Release Descriptor

This repository is a releasable AI-Verse component and publishes its owner acceptance through the shared `ai-verse.component-release/v1` descriptor at `release/component-release.json`.

The descriptor's `revision` names the exact Distribution source commit being accepted. It is distinct from the later metadata-only commit that publishes the descriptor.

## Native owner evidence

- `.github/workflows/ci.yml` is the designated native Distribution CI workflow.
- `.github/workflows/repository-network-regression.yml` is the designated Distribution acceptance workflow for release and owner-boundary regressions.
- `.github/workflows/release-descriptor.yml` validates the descriptor and requires successful runs of both designated workflows on the exact descriptor revision.

A successful descriptor gate means only that Distribution accepts that exact source revision under Distribution's own component contract. It does not qualify, admit, promote, or mark healthy any Core release set. Whole-product composition, member preservation, channels, and recovery remain governed by Distribution's release-set qualification and promotion contracts.
