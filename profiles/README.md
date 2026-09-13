# Distribution Profiles

Profiles are named software selections. They are never permission or authority bundles.

The machine-readable profile contract is `profiles/profiles.json`.

## Core

OS + Brain + Memory + Skills + Data.

Current admitted release set:

`core-first-member-beta-2026-09-13`

## Agent

Core + Gateway + Automations + Multiple Bots, plus Token when Token reaches the public-beta inclusion gate.

The profile exists in the resolver, but no immutable Agent release set is currently admitted. `aiverse install --profile agent` therefore fails closed and prints the concrete blockers.

## Full

Agent + Connections + Dashboard + Apps when those owners are released.

Full remains unavailable until an exact compatible release set passes acceptance.

## Custom

Explicit selected components from one admitted compatible release set.

Custom does not permit arbitrary moving refs or cross-release version mixing.

## Authority rule

A profile may select software.

It may not silently:

- transfer Brain strategic ownership;
- grant external connection access;
- authorize Skills or tools;
- initialize every workspace;
- widen Bot permissions;
- expose remote services.

Those remain explicit owner or host operations.
