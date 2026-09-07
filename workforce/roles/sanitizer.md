# Sanitizer Role Contract

## Owns

Allow-list and deny-list enforcement, secret and private-path detection, personal-context checks, coverage reporting, and redacted findings.

## Produces

A bounded `PASS`, `FAIL`, or `BLOCKED` record containing only rule, severity, path, coverage, and redacted classification.

## Does not own

Publishing, release acceptance, or retention of scan history.
