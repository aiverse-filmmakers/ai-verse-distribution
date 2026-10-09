#!/usr/bin/env bash
set -euo pipefail

GATEWAY_SHA="1772b75e2add73a524715f746e87b3a6b5561bf6"
OS_SHA="4f03849444b1d01ad81317bf0fece082d5a30e79"
MEMORY_SHA="f1327be48ba2ee0043959021365e6dbb9dcb1d3a"

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
GATEWAY="$ROOT/gateway"
OS="$ROOT/os"
MEMORY="$ROOT/memory"
HOST_CONFIG="$ROOT/os-host.json"

clone_exact() {
  local repo="$1"
  local sha="$2"
  local dest="$3"
  git clone --quiet "https://github.com/aiverse-filmmakers/${repo}.git" "$dest"
  git -C "$dest" checkout --quiet --detach "$sha"
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

clone_exact "AI-Verse-Gateway" "$GATEWAY_SHA" "$GATEWAY"
clone_exact "AI-Verse-OS" "$OS_SHA" "$OS"
clone_exact "AI-Verse-Memory" "$MEMORY_SHA" "$MEMORY"

# Rebuild the canonical J2 Context Ladder fixture on the exact frozen OS.
for workspace in alpha beta; do
  mkdir -p "$OS/workspaces/$workspace/context"
  if [ "$workspace" = "alpha" ]; then NAME="Alpha"; else NAME="Beta"; fi
  cat > "$OS/workspaces/$workspace/WORKSPACE.yaml" <<YAML
schema_version: "2.0"
id: "$workspace"
name: "$NAME"
type: project
status: active
purpose: "Purpose Context exact-candidate Context Ladder qualification."
domains: []
owners: []
success_criteria: []
canonical_sources: []
connections: []
current_context: context/CURRENT.md
YAML
done
cat > "$OS/workspaces/alpha/context/CURRENT.md" <<'MD'
# Current Workspace Context

## Objective

Prove Context Ladder composition across Gateway, OS, and Memory.

## Current state

J2-CANONICAL-SOURCE-ALPHA render profile is ACEScg.
MD
cat > "$OS/workspaces/beta/context/CURRENT.md" <<'MD'
# Current Workspace Context

## Current state

Beta workspace is isolated from Alpha.
MD

python "$MEMORY/scripts/install.py" --target "$OS" --source-dir "$MEMORY"
python "$OS/scripts/ai_verse_host_adapter.py" --root "$OS" --write-config "$HOST_CONFIG"
test -f "$OS/scripts/ai-verse-memory/memory.py"
grep -Fq 'ai-verse-memory' "$OS/.aiverse/extensions/registry.json"

pushd "$GATEWAY" >/dev/null
npm install --no-audit --no-fund

# The real composed Context Ladder path: Gateway runtime + host adapter + exact OS + exact Memory.
OS_ROOT="$OS" HOST_CONFIG="$HOST_CONFIG" node scripts/test-context-ladder-integrated-composition.mjs

# Runtime integration contracts that govern Purpose admission, precedence, refresh,
# progressive context, deep retrieval, context pressure, and fail-closed recovery.
node --test \
  test/context-governor.test.mjs \
  test/deep-context-tool.test.mjs \
  test/progressive-context.test.mjs \
  test/purpose-envelope.test.mjs \
  test/purpose-precedence.test.mjs \
  test/purpose-refresh.test.mjs \
  test/purpose-relevance.test.mjs \
  test/purpose-unavailable.test.mjs \
  test/security-and-recovery.test.mjs \
  test/state-linearizability.test.mjs
popd >/dev/null

echo "Exact Purpose Context Ladder/runtime integration: PASS"
