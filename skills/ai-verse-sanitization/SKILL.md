---
name: ai-verse-sanitization
description: Use when a named AI-VERSE artifact must be checked for secrets, private runtime material, unapproved paths, or missing provenance before review or release.
---

# AI-VERSE Sanitization

Inspect one explicitly supplied candidate and return bounded findings without retaining sensitive contents.

## Procedure

1. Confirm the candidate root, allow-list, deny-list, detection rules, and provenance inputs.
2. Scan paths and readable content deterministically.
3. Record only rule, severity, path, coverage, and a redacted classification.
4. Return `PASS` only when coverage is complete and no blocking finding exists.
5. Return `BLOCKED` when coverage is incomplete, provenance is missing, or private material is found.
6. Hand findings to QA; never waive a finding or publish material.

Never inspect a deployed owner profile or copy live state into a package.
