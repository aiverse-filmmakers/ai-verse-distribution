---
name: ai-verse-audit
description: Use when the owner asks whether the AI-VERSE setup is useful, safe, connected, or ready for its next improvement; produce a read-only gap report.
---

# AI-VERSE Audit

Inspect the operating layer without changing it.

## Review areas

1. **Identity:** Can a fresh agent answer what the owner and project are trying to achieve from verified records?
2. **Reach:** Are approved tools and connections named with clear boundaries, without exposing credentials?
3. **Workflows:** Do the installed AI-VERSE skills turn common goals into repeatable outputs, and are host capabilities reused rather than duplicated?
4. **Rhythm:** Is there a clear user-triggered review and improvement habit, with no hidden schedule or unexplained model use?

## Output

Return:

- `READY`, `PARTIAL`, or `BLOCKED`;
- evidence inspected;
- one finding per gap, ordered by impact;
- the smallest recommended improvement;
- any owner decision required.

The audit is read-only. It does not install skills, change configuration, create schedules, or declare a release.
