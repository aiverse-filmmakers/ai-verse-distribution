#!/usr/bin/env bash
set -euo pipefail

OS_SHA="4f03849444b1d01ad81317bf0fece082d5a30e79"
DATA_SHA="f8978f8f7a1bc94edecddc2662112233289159a3"
MEMORY_SHA="f1327be48ba2ee0043959021365e6dbb9dcb1d3a"

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

clone_exact() {
  local repo="$1"
  local sha="$2"
  local dest="$3"
  git clone --quiet "https://github.com/aiverse-filmmakers/${repo}.git" "$dest"
  git -C "$dest" checkout --quiet --detach "$sha"
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

clone_exact "AI-Verse-OS" "$OS_SHA" "$ROOT/os"
clone_exact "AI-Verse-Data" "$DATA_SHA" "$ROOT/data"
clone_exact "AI-Verse-Memory" "$MEMORY_SHA" "$ROOT/memory"

# Data owner contract used by Purpose Context: exact values, status, freshness,
# provenance, and no canonical-row copying across the projection boundary.
pushd "$ROOT/data" >/dev/null
npm install --no-audit --no-fund
npm run build
node --test \
  dist/test/purpose-current-value-status.test.js \
  dist/test/purpose-current-values-freshness.test.js \
  dist/test/purpose-current-values-provenance.test.js \
  dist/test/purpose-current-values.test.js \
  dist/test/purpose-no-row-copy.test.js
popd >/dev/null

# Memory owner contract used by Purpose Context: bounded, exact-scope historical
# evidence only, never current strategic authority.
pushd "$ROOT/memory" >/dev/null
python -m unittest tests.test_purpose_history
popd >/dev/null

# OS consumer-side integration boundaries against those owner contracts.
pushd "$ROOT/os" >/dev/null
node scripts/test-purpose-data-current-value-boundary.mjs
node scripts/test-purpose-data-current-state.mjs
node scripts/test-purpose-data-source-descent.mjs
node scripts/test-purpose-memory-history-boundary.mjs
node scripts/test-purpose-memory-history-read.mjs
popd >/dev/null

echo "Exact Data/Memory Purpose integration: PASS"
