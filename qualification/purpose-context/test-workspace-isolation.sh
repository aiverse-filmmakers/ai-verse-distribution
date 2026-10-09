#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CANDIDATE="$ROOT/qualification/purpose-context/candidate.json"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

OS_SHA="$(python - "$CANDIDATE" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
if p.get('status') != 'blocked' or p.get('profile') != 'core':
    raise SystemExit('qualification must use the blocked Core candidate')
components = {x['id']: x for x in p['components']}
ref = components['ai-verse-os']['revision']
if len(ref) != 40 or any(c not in '0123456789abcdef' for c in ref):
    raise SystemExit('ai-verse-os is not pinned to an exact commit SHA')
print(ref)
PY
)"
OS_ROOT="$WORK/AI-Verse-OS"

git init -q "$OS_ROOT"
git -C "$OS_ROOT" remote add origin https://github.com/aiverse-filmmakers/AI-Verse-OS.git
git -C "$OS_ROOT" fetch --quiet --depth 1 origin "$OS_SHA"
git -C "$OS_ROOT" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$OS_ROOT" rev-parse HEAD)" = "$OS_SHA"

# Canonical workspace ownership must create/evolve only the requested workspace,
# reject traversal/secrets/authority widening, and preserve unrelated workspace state.
node "$OS_ROOT/scripts/test-workspace-owner.mjs"

# Purpose reads must reject missing/traversal/symlinked workspace boundaries and
# must not retain deleted workspace data through a cache.
node "$OS_ROOT/scripts/test-purpose-context-workspace-boundary.mjs"

# Adversarial isolation: operator cannot descend into workspaces, workspace A cannot
# read workspace B or operator state, provenance cannot point at sibling scopes,
# and malformed ownership/path redirects fail closed.
node "$OS_ROOT/scripts/test-purpose-context-security-hardening.mjs"

# Explicit cross-scope relationships may retain canonical refs, but must never
# resolve, enumerate, inherit, or ingest data from the referenced foreign scope.
node "$OS_ROOT/scripts/test-purpose-context-relationships.mjs"

# Qualification must not mutate the frozen candidate checkout itself.
test -z "$(git -C "$OS_ROOT" status --porcelain --untracked-files=no)"

printf 'Exact candidate workspace isolation: PASS\nOS=%s\n' "$OS_SHA"
