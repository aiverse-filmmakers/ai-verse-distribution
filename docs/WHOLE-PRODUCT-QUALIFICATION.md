# Whole-Product Qualification

Slice 5.3 adds one Distribution qualification layer above exact candidate admission.

The qualification gate answers one question:

> Has this exact already-admitted candidate also passed the required composed-product evidence needed before any promotion decision can be considered?

It does not promote a release, modify a channel, rewrite Repository State, replace owner health, or mutate a member installation.

## Inputs

The gate consumes four existing evidence boundaries:

1. the exact candidate admitted by `candidate_admission.py`, including its frozen System, Registry, Repository State, owner-descriptor/native-CI, compatibility, toolchain and drift bindings;
2. one canonical `ai-verse.release-preservation/v1` result for the exact candidate Distribution revision;
3. one Distribution composed-acceptance result for the same exact candidate and Distribution revision;
4. the candidate compatibility platform scope and exact component set.

The composed-acceptance input uses `aiverse.distribution-composed-acceptance/v1`. For every supported platform it records the clean-install, status, doctor and health gates plus the exact component status/doctor outcome and executable run evidence.

A component is qualification-ready only when its composed status and doctor outcome are both `ready`. Results such as `setup-required`, `degraded`, `blocked`, missing evidence, or a failed platform gate stop qualification.

## Preservation consumption

The qualification gate consumes the canonical System whole-release preservation result rather than defining another preservation format. The result must be update-safe, target the exact candidate, bind the exact Distribution revision, cover the candidate platform scope, pass clean install, upgrade, restart/recovery and authority preservation, contain accepted state-preservation outcomes, contain non-blocked migration evidence, pass destructive-negative tests and include exact-revision executable evidence.

## Output

A passing result uses:

`aiverse.distribution-whole-product-qualification/v1`

It binds:

- the exact candidate-evidence file and digest;
- the frozen System governance revision and contracts;
- the exact Registry binding;
- the exact scoped Repository State binding;
- the candidate compatibility digest;
- each exact owner revision, descriptor digest and native workflow run;
- the canonicalized preservation-result digest;
- the canonicalized composed-acceptance digest.

The output explicitly declares that it is qualification evidence only. It has no promotion, channel, Registry, Repository State, owner-health or member-state authority.

Any bound-input change requires a new qualification result.

## CLI

```bash
python scripts/build-whole-product-qualification.py CANDIDATE_ID \
  --preservation qualification/CANDIDATE_ID/release-preservation.json \
  --composed-acceptance qualification/CANDIDATE_ID/composed-acceptance.json \
  --output qualification/CANDIDATE_ID/whole-product-qualification.json
```

The command is read-only with respect to release catalogs and channels. Writing the requested output file does not promote the candidate.

## Promotion boundary

Promotion remains a separate Slice 5.3 task. A passing whole-product qualification result is necessary evidence, not permission to alter `core_promotions.json`, the default channel, lineage, automatic-update state, or any member installation.
