#!/usr/bin/env bash
set -euo pipefail

GATEWAY_SHA="1772b75e2add73a524715f746e87b3a6b5561bf6"
RELEASE_SET="core-purpose-context-candidate-2026-10-09"
OS_SHA="4f03849444b1d01ad81317bf0fece082d5a30e79"
BRAIN_SHA="69f7912eeb35f0178f6952ff0554aec8d7f2c496"
MEMORY_SHA="f1327be48ba2ee0043959021365e6dbb9dcb1d3a"
SKILLS_SHA="afde5c06307fba7d074de2929c2eb6c3dc6bdab8"
DATA_SHA="f8978f8f7a1bc94edecddc2662112233289159a3"

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
GATEWAY="$ROOT/gateway"
OS="$ROOT/os"
HOST_CONFIG="$ROOT/os-host.json"
INSTALL_JSON="$ROOT/install.json"
export AIVERSE_DISTRIBUTION_HOME="$ROOT/distribution-home"
export HOME="$ROOT/home"
export USERPROFILE="$ROOT/home"
mkdir -p "$HOME"

clone_exact() {
  local repo="$1"
  local sha="$2"
  local dest="$3"
  git clone --quiet "https://github.com/aiverse-filmmakers/${repo}.git" "$dest"
  git -C "$dest" checkout --quiet --detach "$sha"
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

clone_exact "AI-Verse-Gateway" "$GATEWAY_SHA" "$GATEWAY"

# Stage the already-frozen blocked candidate only inside this qualification job.
# This reuses Distribution's trusted exact-owner lifecycle adapters and does not
# admit the candidate into any canonical release channel.
python scripts/prepare-purpose-candidate-qualification.py >/dev/null
python -m pip install . >/dev/null
python -m aiverse_distribution.cli install \
  --profile core \
  --root "$OS" \
  --release-set "$RELEASE_SET" \
  --json > "$INSTALL_JSON"

python - "$INSTALL_JSON" "$OS_SHA" "$BRAIN_SHA" "$MEMORY_SHA" "$SKILLS_SHA" "$DATA_SHA" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
expected = dict(zip(
    ['ai-verse-os','ai-verse-brain','ai-verse-memory','ai-verse-skills','ai-verse-data'],
    sys.argv[2:]
))
assert p.get('state') == 'installed', p
for component, sha in expected.items():
    receipt = p['components'][component]
    assert receipt['revision'] == sha, (component, receipt.get('revision'), sha)
PY

# Rebuild the canonical J2 Context Ladder fixture on the candidate-installed OS.
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

# Establish lifecycle authority through the same trusted setup path used by Core.
python -m aiverse_distribution.cli setup --workspace alpha --json >/dev/null
python -m aiverse_distribution.cli status --json > "$ROOT/status.json"
python - "$ROOT/status.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
assert p.get('state') == 'ready', p
for component in ('ai-verse-memory','ai-verse-data','ai-verse-brain'):
    item = p['components'][component]
    assert item.get('enabled') is True, (component, item)
PY

python "$OS/scripts/ai_verse_host_adapter.py" --root "$OS" --write-config "$HOST_CONFIG"
test -f "$OS/scripts/ai-verse-memory/memory.py"
grep -Fq 'ai-verse-memory' "$OS/.aiverse/extensions/registry.json"

pushd "$GATEWAY" >/dev/null
npm install --no-audit --no-fund

# The real composed Context Ladder path: accepted Gateway runtime + candidate-installed
# exact Core + lifecycle-authorized Memory through the OS host adapter.
OS_ROOT="$OS" HOST_CONFIG="$HOST_CONFIG" node scripts/test-context-ladder-integrated-composition.mjs

# Runtime integration contracts governing Purpose admission, precedence, refresh,
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
