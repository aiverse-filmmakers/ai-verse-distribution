# AGENCY-OS Distribution

This private repository contains the generated AGENCY-OS Architect profile and the source contracts used to keep an AGENCY-OS workforce organized.

## What this installs

The package gives Hermes one operational Architect profile with:

- a clear project-leader identity;
- state-driven project context and work tracking;
- bounded, user-triggered initiative with no hidden background schedule;
- source contracts for QA, Release, Sanitizer, and HR boundaries;
- reusable project-state templates.

The source contracts describe the wider workforce. They do not copy or deploy anyone's private runtime profile. Independent QA and Release remain separate authorities when a real team is configured.

## Install

Requirements: Hermes Agent `0.20.5` or newer and access to this private repository.

```bash
hermes profile install github.com/aiverse-filmmakers/agency-os-distribution --alias
```

Configure your own model provider and credentials locally after installation. This repository never supplies credentials, memories, sessions, or runtime databases.

## Use

Start the profile with the generated `agency-os` command, or select it through Hermes. For a real project, copy the templates from `templates/project-state/` into that project's own `project-state/` directory and fill them with the project's facts. Keep project state separate from the Architect's private memory.

When work is approved, tell the Architect what outcome you want and say `go ahead`. The Architect reads the state, chooses the next legitimate task, routes specialist work, and reports the evidence in plain language.

## Update and rollback

```bash
hermes profile update agency-os
```

Updates replace package-owned files but preserve your local memories, sessions, credentials, and user data. Pin a known-good Git commit or tag when you need a rollback. Do not edit the generated repository directly; changes belong in Golden and are exported again.

## Current status

This is a private Phase 3 candidate. It is organized and installable as an Architect profile, but the member-ready gate still requires independent QA and Release evidence for the exact published commit.
