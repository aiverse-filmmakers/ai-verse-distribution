#!/usr/bin/env bash
set -euo pipefail

RELEASE_SET="agent-purpose-context-candidate-2026-10-09"
EXPECTED_REFS='{"ai-verse-os":"4f03849444b1d01ad81317bf0fece082d5a30e79","ai-verse-brain":"69f7912eeb35f0178f6952ff0554aec8d7f2c496","ai-verse-memory":"f1327be48ba2ee0043959021365e6dbb9dcb1d3a","ai-verse-skills":"afde5c06307fba7d074de2929c2eb6c3dc6bdab8","ai-verse-data":"f8978f8f7a1bc94edecddc2662112233289159a3","ai-verse-gateway":"1772b75e2add73a524715f746e87b3a6b5561bf6","ai-verse-automations":"caaed83b98026dd955640fc015d181529b91a1c6","ai-verse-multiple-bots":"c600e2bc014351a61e1c0e2673fc63f5d5fa54ec","ai-verse-token":"23b7b8ecbc9d9ef267f5e10449f785eb11107dd4"}'

# Stage the blocked Core candidate through the existing trusted qualification path,
# then stage one blocked Agent candidate containing that exact Core plus the
# exact Purpose-aware Gateway and unchanged admitted Agent tail components.
python -m unittest tests.test_purpose_context_candidate
python scripts/prepare-purpose-candidate-qualification.py >/dev/null
python scripts/prepare-purpose-agent-candidate-qualification.py >/dev/null

# Keep the canonical composed Goal/Learning acceptance reusable, but bind this
# qualification run to the exact staged Agent candidate rather than its historic
# Video Editor default.
python - <<'PY'
from pathlib import Path
path = Path('tests/acceptance/composed_goal_learning_acceptance.py')
text = path.read_text(encoding='utf-8')
old = 'RELEASE = "agent-video-editor-rc1-2026-10-04"'
new = 'RELEASE = os.environ.get("AI_VERSE_ACCEPTANCE_RELEASE_SET", "agent-video-editor-rc1-2026-10-04")'
if old not in text:
    raise RuntimeError('composed Goal/Learning qualification anchor changed')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
PY

python -m pip install . >/dev/null

export AI_VERSE_ACCEPTANCE_RELEASE_SET="$RELEASE_SET"
export AI_VERSE_ACCEPTANCE_EXPECTED_REFS="$EXPECTED_REFS"

# Full clean-machine Agent composition: all nine exact refs, owner lifecycle,
# Gateway Goal path, Bots collaboration, Automations wake, Token projection,
# state preservation and restart behavior.
python tests/acceptance/agent_acceptance.py

# Additional composed runtime proof on the same exact staged candidate:
# Gateway Goal binding plus the OS/Brain/Skills learning and reuse path.
python tests/acceptance/composed_goal_learning_acceptance.py

echo "Exact Purpose Agent/composed qualification: PASS"
