---
name: ai-verse-connections
description: Use when recording or reviewing which approved tools, services, files, or data sources AI-VERSE may reach without storing credentials in the project package.
---

# AI-VERSE Connections

Maintain a clear map of approved reach without exposing secrets.

## Record

For each connection, record only:

- name and owner;
- purpose and allowed actions;
- data classification;
- local configuration location, without values;
- approval state;
- test or health evidence;
- revocation or stop condition.

## Rules

- Credentials belong in the host's secure credential mechanism, never in project state or this package.
- A listed connection is not permission to use it for every task.
- Ask before adding, widening, or testing a connection that can affect external systems.
- Report unavailable access plainly instead of inventing a result.
