---
name: agency-os-sanitization-runbook
description: Runs bounded, deterministic, redacted checks over an explicitly supplied AGENCY-OS artifact.
---

# AGENCY-OS Sanitization Runbook

## Outcome

Given one named candidate root and approved policy inputs, return a structured result without retaining raw secrets or private content.

## Procedure

1. Confirm the exact candidate root, allow-list, deny-list, and detection rules.
2. Scan paths and readable content deterministically.
3. Record only rule, severity, path, coverage, and redacted classification.
4. Return `PASS` only when coverage is complete and no blocking finding exists.
5. Return `BLOCKED` when coverage is incomplete or provenance is missing.
6. Hand findings to QA. Never waive a finding or publish material.

The runbook never inspects a deployed owner profile, copies LIVE state, or stores scan history.
