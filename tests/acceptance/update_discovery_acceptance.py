"""Public-command stale-catalog qualification using genuine admitted Core releases.

Only the disposable updater fixture receives a deliberately older packaged
catalog. No fake Core release, receipt rewrite or member-state adoption is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

OLD_DISTRIBUTION = '37bdf4d9526abf59e5ce5b0cf783ee349428f3d7'
OLD_CORE = 'core-shared-skills-candidate-2026-10-23-v4'
NEW_CORE = 'core-tool-placement-candidate-2026-10-23'
REPOSITORY = 'https://github.com/aiverse-filmmakers/ai-verse-distribution.git'


def run(*argv, cwd=None, capture=False):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None, check=False)
    if result.returncode:
        raise RuntimeError(f'Acceptance command failed ({result.returncode}): {argv[0]}\n'
                           f'{result.stdout or ""}\n{result.stderr or ""}')
    return result.stdout if capture else ''


def main():
    source = Path(__file__).resolve().parents[2]
    base = Path(tempfile.mkdtemp(prefix='av-discovery-'))
    old = base / 'old'
    old.mkdir()
    run('git', 'init', cwd=old)
    run('git', 'remote', 'add', 'origin', REPOSITORY, cwd=old)
    run('git', 'fetch', '--depth=1', 'origin', OLD_DISTRIBUTION, cwd=old)
    run('git', '-c', 'core.autocrlf=false', 'checkout', '--detach', 'FETCH_HEAD', cwd=old)
    member, stack = base / 'member', base / 's'
    # Use the canonical Python bootstrap stage with the already-qualified host
    # Python; platform wrappers prepare this same stage when Python is absent.
    run(sys.executable, old / 'scripts/project-bootstrap.py', '--project', member, '--stack', stack)
    marker = json.loads((stack / 'project.json').read_text())
    python, launcher = marker['python'], marker['launcher']

    def command(*args):
        return json.loads(run(python, launcher, *args, '--json', capture=True))

    before = command('status')
    assert before['release_set_id'] == OLD_CORE and before['state'] == 'ready'
    original_plan = command('update', '--plan')
    assert original_plan['to'] == OLD_CORE and original_plan['noop'] is True
    payload = {
        'operator/profile/member-note.md': b'Private member preference fixture.\n',
        'workspaces/member-work/WORKSPACE.yaml': b'schema_version: "2.0"\nid: member-work\nname: Member work\ntype: test\nstatus: active\npurpose: Preservation fixture\n',
        'workspaces/member-work/knowledge/private-note.md': b'Private workspace fixture.\n',
        'apps/member-tool/package.json': b'{"private":true,"name":"member-tool"}\n',
    }
    for path, content in payload.items():
        target = member / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    fixture = base / 'transport'
    fixture.mkdir()
    shutil.copytree(source / 'src', fixture / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    for name in ('pyproject.toml', 'README.md'):
        shutil.copyfile(source / name, fixture / name)
    package = fixture / 'src/aiverse_distribution'
    shutil.rmtree(package / 'catalog')
    shutil.copytree(old / 'src/aiverse_distribution/catalog', package / 'catalog')
    # This is the initial one-time tooling refresh in a disposable qualification
    # fixture. It intentionally ships the older real catalog to simulate time
    # passing after the transport was installed, before the next Core release.
    run(python, launcher, '--exec', python, '-m', 'pip', 'install', '--no-deps', fixture)
    home = stack / 'd'
    pointer = home / 'updater/active.json'
    receipt_before = (home / 'locks/current.json').read_bytes()
    preview = command('update', '--plan')
    assert preview['from'] == OLD_CORE and preview['to'] == NEW_CORE and not preview['noop']
    assert not pointer.exists()
    assert (home / 'locks/current.json').read_bytes() == receipt_before
    applied = command('update')
    after = command('status')
    assert after['release_set_id'] == NEW_CORE and after['state'] == 'ready'
    assert all(c['state'] == 'ready' for c in after['components'].values())
    assert command('doctor')['ok'] is True
    assert command('update')['noop'] is True
    assert all((member / path).read_bytes() == content for path, content in payload.items())
    selected = json.loads(pointer.read_text())
    assert len(selected['revision']) == 40 and selected['repository'] == REPOSITORY
    # Offline transport must refuse a latest-release claim, while cached local
    # status/doctor remain usable. Only the network boundary is doubled.
    offline = """import sys
from unittest.mock import patch
from aiverse_distribution import entrypoint, update_discovery as d
original=d._git
def git(*args, **kwargs):
    if args[0]=='ls-remote': raise d.DiscoveryError('Latest-release status is unknown: offline')
    return original(*args, **kwargs)
with patch.object(d, '_git', side_effect=git):
    assert entrypoint.main(['update','--json'])==2
    assert entrypoint.main(['status','--json'])==0
    assert entrypoint.main(['doctor','--json'])==0
"""
    run(python, launcher, '--exec', python, '-I', '-B', '-c', offline)
    report = {'old_updater_noop': OLD_CORE, 'discovered_core': after['release_set_id'],
              'selected_snapshot': selected['revision'], 'preview_preserved_receipt': True,
              'member_files_preserved': len(payload), 'all_components_ready': True,
              'doctor': True, 'repeat_noop': True, 'offline_refusal_and_local_health': True,
              'fixture_root': str(base)}
    (base / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
