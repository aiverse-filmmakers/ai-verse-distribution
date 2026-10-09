#!/usr/bin/env bash
set -euo pipefail

RELEASE_SET="core-purpose-context-candidate-2026-10-09"
OS_SHA="4f03849444b1d01ad81317bf0fece082d5a30e79"
BRAIN_SHA="69f7912eeb35f0178f6952ff0554aec8d7f2c496"
MEMORY_SHA="f1327be48ba2ee0043959021365e6dbb9dcb1d3a"
SKILLS_SHA="afde5c06307fba7d074de2929c2eb6c3dc6bdab8"
DATA_SHA="f8978f8f7a1bc94edecddc2662112233289159a3"

# Machine-gate the immutable candidate declaration first.
python -m unittest tests.test_purpose_context_candidate
python scripts/prepare-purpose-candidate-qualification.py >/dev/null
python -m pip install . >/dev/null

# Prove the staged qualification set is still exactly the frozen five-component set.
python - "$OS_SHA" "$BRAIN_SHA" "$MEMORY_SHA" "$SKILLS_SHA" "$DATA_SHA" <<'PY'
import json, sys
from pathlib import Path
p = json.loads(Path('qualification/purpose-context/candidate.json').read_text(encoding='utf-8'))
expected = dict(zip(
    ['ai-verse-os','ai-verse-brain','ai-verse-memory','ai-verse-skills','ai-verse-data'],
    sys.argv[1:]
))
assert p['release_set_id'] == 'core-purpose-context-candidate-2026-10-09', p
refs = p.get('refs') or p.get('components') or {}
for component, sha in expected.items():
    value = refs.get(component)
    if isinstance(value, dict):
        value = value.get('revision') or value.get('ref') or value.get('sha')
    assert value == sha, (component, value, sha)
PY

# Run the canonical composed Core acceptance on one exact installed system.
# This exercises all changed Core owners together, not separate green runs.
AI_VERSE_ACCEPTANCE_RELEASE_SET="$RELEASE_SET" \
  python tests/acceptance/profile_acceptance.py core

echo "Exact composed Core Purpose candidate acceptance: PASS"
