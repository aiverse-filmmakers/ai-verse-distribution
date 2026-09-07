---
name: ai-verse-release
description: Use when an AI-VERSE package or skill set needs deterministic packaging, privacy evidence, versioning, upgrade testing, or rollback verification.
---

# AI-VERSE Release

A release is a verified projection from Golden, not a hand-edited copy.

## Gate order

1. Confirm the source revision is committed and the allow-list is explicit.
2. Validate provenance, licensing, privacy scans, and generated integrity.
3. Test the package on each declared host with disposable data.
4. Confirm upgrade and rollback preserve host-owned data.
5. Publish only the exact verified revision.
6. Record version, digest, evidence, and known limitations.

Never publish a dirty source tree, include credentials or private runtime state, or call a candidate member-ready while a release gate is blocked.
