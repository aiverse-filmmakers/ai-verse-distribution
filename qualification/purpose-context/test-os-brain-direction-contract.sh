#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CANDIDATE="$ROOT/qualification/purpose-context/candidate.json"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mapfile -t REFS < <(python - "$CANDIDATE" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
if p.get('status') != 'blocked' or p.get('profile') != 'core':
    raise SystemExit('qualification must use the blocked Core candidate')
components = {x['id']: x for x in p['components']}
for name in ('ai-verse-os', 'ai-verse-brain'):
    ref = components[name]['revision']
    if len(ref) != 40 or any(c not in '0123456789abcdef' for c in ref):
        raise SystemExit(f'{name} is not pinned to an exact commit SHA')
    print(ref)
PY
)
OS_SHA="${REFS[0]}"
BRAIN_SHA="${REFS[1]}"
OS_ROOT="$WORK/AI-Verse-OS"
BRAIN_ROOT="$WORK/AI-Verse-Brain"

clone_exact() {
  local repo="$1" sha="$2" dest="$3"
  git init -q "$dest"
  git -C "$dest" remote add origin "$repo"
  git -C "$dest" fetch --quiet --depth 1 origin "$sha"
  git -C "$dest" checkout --quiet --detach FETCH_HEAD
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

clone_exact https://github.com/aiverse-filmmakers/AI-Verse-OS.git "$OS_SHA" "$OS_ROOT"
clone_exact https://github.com/aiverse-filmmakers/AI-Verse-Brain.git "$BRAIN_SHA" "$BRAIN_ROOT"

# First prove the exact OS ownership primitives themselves.
node "$OS_ROOT/scripts/test-direction-owner.mjs"
node "$OS_ROOT/scripts/test-current-context.mjs"

# Install exactly the frozen Brain candidate, never a branch head.
python -m pip install -e "$BRAIN_ROOT"

# Register Brain only inside this disposable qualification host.
export OS_ROOT
python - <<'PY'
import os
from pathlib import Path
manifest = Path(os.environ['OS_ROOT']) / 'AI-VERSE.yaml'
text = manifest.read_text(encoding='utf-8')
needle = 'extensions:\n  memory:\n'
if needle not in text:
    raise SystemExit('exact OS manifest extension layout changed; review qualification fixture')
replacement = (
    'extensions:\n'
    '  brain:\n'
    '    supported: true\n'
    '    enabled: true\n'
    '  memory:\n'
)
manifest.write_text(text.replace(needle, replacement, 1), encoding='utf-8')
PY

mkdir -p "$OS_ROOT/operator/profile" "$OS_ROOT/operator/context"
cat > "$OS_ROOT/operator/profile/goals.md" <<'EOF'
# Operator Goals

## Current horizon

- Preserve the existing OS goal through handover
EOF
cat > "$OS_ROOT/operator/context/CURRENT.md" <<'EOF'
# Current Operator Context

## Current priorities

- Ship the current milestone safely
EOF

node "$OS_ROOT/scripts/direction-owner.mjs" status --root "$OS_ROOT" --scope operator | grep -q '"owner": "os"'
node "$OS_ROOT/scripts/direction-owner.mjs" assert-strategic-write --root "$OS_ROOT" --scope operator
ai-verse-brain init "$OS_ROOT" --apply

# Brain installation must not silently steal ownership.
node "$OS_ROOT/scripts/direction-owner.mjs" status --root "$OS_ROOT" --scope operator | grep -q '"owner": "os"'
set +e
ai-verse-brain onboard "$OS_ROOT" --scope operator --answers <(printf '%s' '{"desired_state":"parallel goal","success_definition":"must not write"}') --apply > "$WORK/pre-handover-onboard.json"
status=$?
set -e
test "$status" -eq 2

# Explicit handover must preserve/import existing OS direction with provenance.
ai-verse-brain direction-owner "$OS_ROOT" --scope operator --handover-to-brain > "$WORK/handover-plan.json"
grep -q 'Preserve the existing OS goal through handover' "$WORK/handover-plan.json"
grep -q 'Ship the current milestone safely' "$WORK/handover-plan.json"
ai-verse-brain direction-owner "$OS_ROOT" --scope operator --handover-to-brain --apply --confirm-import > "$WORK/handover-result.json"
grep -q '"owner": "brain"' "$WORK/handover-result.json"
test -f "$OS_ROOT/.aiverse/direction/ownership.json"
test -f "$OS_ROOT/.aiverse/direction/views/operator.md"
grep -q 'AI-Verse Brain is the strategic direction owner' "$OS_ROOT/.aiverse/direction/views/operator.md"

# OS must independently observe Brain ownership and refuse strategic writes.
set +e
node "$OS_ROOT/scripts/direction-owner.mjs" assert-strategic-write --root "$OS_ROOT" --scope operator > "$WORK/os-write.out" 2> "$WORK/os-write.err"
status=$?
set -e
test "$status" -eq 3
grep -q 'owned by Brain' "$WORK/os-write.err"

python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ['OS_ROOT'])
intent_dir = root / 'operator' / 'brain' / 'intent'
objects = [json.loads(p.read_text(encoding='utf-8')) for p in intent_dir.glob('*.json')]
confirmed = [o for o in objects if o.get('status') in {'CONFIRMED', 'ACTIVE'}]
statements = {o.get('payload', {}).get('statement') for o in confirmed}
expected = {
    'Preserve the existing OS goal through handover',
    'Ship the current milestone safely',
}
if not expected.issubset(statements):
    raise SystemExit(f'missing imported statements: {expected - statements}')
for obj in confirmed:
    if obj.get('payload', {}).get('statement') not in expected:
        continue
    provenance = obj['payload'].get('provenance', {})
    if provenance.get('source') != 'ai-verse-os':
        raise SystemExit('imported intent lost OS provenance')
    if not provenance.get('source_path') or not provenance.get('source_sha256'):
        raise SystemExit('imported intent missing path/hash provenance')
    if provenance.get('import_confirmed') is not True:
        raise SystemExit('imported intent was not explicitly confirmed')
PY

# Operational current state remains valid after handover, frozen OS strategy does not.
cat >> "$OS_ROOT/operator/context/CURRENT.md" <<'EOF'

## Current state

- Operational fact survives handover
EOF
python - <<'PY'
import os
from aiverse_brain.local_host import ReadOnlyContextHost
result = ReadOnlyContextHost(os.environ['OS_ROOT']).read_context('operator')
text = result['current_context']
if result.get('direction_owner') != 'brain':
    raise SystemExit('Brain read-only host lost Brain direction ownership')
if result.get('context_resolver') != 'ai-verse-os:scripts/current-context.mjs':
    raise SystemExit('Brain did not use exact OS current-context resolver')
if 'Ship the current milestone safely' in text:
    raise SystemExit('frozen OS priority re-entered active Brain context')
if 'Operational fact survives handover' not in text:
    raise SystemExit('valid operational current state was lost')
if not result.get('direction_refs'):
    raise SystemExit('Brain canonical direction refs were not surfaced')
PY

# Brain loss must remain fail-closed and must not reactivate frozen OS strategy.
rm -rf "$OS_ROOT/operator/brain" "$OS_ROOT/runtime/ai-verse-brain"
set +e
node "$OS_ROOT/scripts/direction-owner.mjs" assert-strategic-write --root "$OS_ROOT" --scope operator > /dev/null 2> "$WORK/after-loss.err"
status=$?
set -e
test "$status" -eq 3
grep -q 'owned by Brain' "$WORK/after-loss.err"
python - <<'PY'
import os
from aiverse_brain.local_host import ReadOnlyContextHost
result = ReadOnlyContextHost(os.environ['OS_ROOT']).read_context('operator')
text = result['current_context']
if result.get('direction_owner') != 'brain':
    raise SystemExit('Brain loss changed direction ownership during read')
if 'Ship the current milestone safely' in text:
    raise SystemExit('Brain loss reactivated frozen OS strategy')
if 'Operational fact survives handover' not in text:
    raise SystemExit('Brain loss hid valid operational state')
PY

# Restore the one test-only tracked edit and prove the exact OS checkout remains clean.
git -C "$OS_ROOT" checkout -- AI-VERSE.yaml
test -z "$(git -C "$OS_ROOT" status --porcelain --untracked-files=no)"

printf 'Exact candidate OS↔Brain direction/ownership contract: PASS\nOS=%s\nBrain=%s\n' "$OS_SHA" "$BRAIN_SHA"
