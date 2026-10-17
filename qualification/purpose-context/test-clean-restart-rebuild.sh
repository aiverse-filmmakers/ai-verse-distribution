#!/usr/bin/env bash
set -euo pipefail

OS_SHA="4f03849444b1d01ad81317bf0fece082d5a30e79"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
OS="$ROOT/os"

git clone --quiet https://github.com/aiverse-filmmakers/AI-Verse-OS.git "$OS"
git -C "$OS" checkout --quiet --detach "$OS_SHA"
test "$(git -C "$OS" rev-parse HEAD)" = "$OS_SHA"

pushd "$OS" >/dev/null
# Canonical delete/rebuild/restart proof: fresh processes must reconstruct the same
# projection from canonical owners, never from a persistent Purpose cache.
node scripts/test-purpose-context-rebuild.mjs
node scripts/test-purpose-context-no-cache.mjs

# Re-prove the ownership-aware canonical current-context resolver that rebuilds
# Purpose after restart and must never resurrect frozen OS strategy.
node scripts/test-current-context.mjs
popd >/dev/null

echo "Exact Purpose clean restart/rebuild qualification: PASS"
