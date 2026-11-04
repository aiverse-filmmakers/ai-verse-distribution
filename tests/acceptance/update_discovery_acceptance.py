"""Public-command stale-catalog qualification using genuine admitted Core releases.

Only the disposable updater fixture receives a deliberately older packaged
catalog. No fake Core release, receipt rewrite or member-state adoption is used.

The default update must carry a member from ANY released Core, however many
releases they skipped, by walking the separately qualified hops in order. Two
sources of "the official updater" are supported:

* published (default): the real official `main` on GitHub. Only meaningful for
  code that is already on `main`, so CI runs it after a merge.
* `--source-mirror`: a throwaway git repository holding THIS checkout, standing in
  for the official repository for this process only. The whole discovery flow
  (select, verify, hand off, update) then runs this checkout's updater, so an
  unmerged change is qualified before it can reach `main`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

OLD_DISTRIBUTION = '25b425ca7b10f384a453b7723df8a87f2449afa6'
OLD_CORE = 'core-tool-placement-candidate-2026-10-23'
REPOSITORY = 'https://github.com/aiverse-filmmakers/ai-verse-distribution.git'


def run(*argv, cwd=None, capture=False):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None, check=False)
    if result.returncode:
        raise RuntimeError(f'Acceptance command failed ({result.returncode}): {argv[0]}\n'
                           f'{result.stdout or ""}\n{result.stderr or ""}')
    return result.stdout if capture else ''


# Runs a lifecycle command with the official-repository constant pointed at the
# mirror, in the same process that owns discovery. The production constant and
# trust checks are untouched.
# Discovery forbids Git's file transport; the throwaway mirror needs it, so the
# wrapper (in the test process only) allows it for this one repository.
MIRROR_PATCH = """
import sys
from unittest.mock import patch
from aiverse_distribution import entrypoint, update_discovery as d
_original_git = d._git
def _mirror_git(*arguments, **kwargs):
    return _original_git('-c', 'protocol.file.allow=always', *arguments, **kwargs)
"""
MIRROR_RUNNER = MIRROR_PATCH + """
with patch.object(d, 'OFFICIAL_REPOSITORY', sys.argv[1]), patch.object(d, '_git', _mirror_git):
    raise SystemExit(entrypoint.main(sys.argv[2:]))
"""


def build_mirror(source, base):
    mirror = base / 'official-mirror'
    mirror.mkdir()
    shutil.copytree(source / 'src', mirror / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    for name in ('pyproject.toml', 'README.md'):
        shutil.copyfile(source / name, mirror / name)
    git = ('git', '-c', 'core.autocrlf=false', '-c', 'user.name=Mirror', '-c', 'user.email=mirror@example.invalid')
    run(*git, 'init', '-b', 'main', cwd=mirror)
    run(*git, 'add', '.', cwd=mirror)
    run(*git, 'commit', '-m', 'mirror of the checked-out updater', cwd=mirror)
    return mirror.resolve().as_uri()


def expected_hops(old_core, new_core):
    from aiverse_distribution.transition_contract import CoreTransitionContract
    path = CoreTransitionContract().update_path(old_core, new_core)
    return [step.target_release for step in path]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-mirror', action='store_true',
                        help='use this checkout as the official updater source instead of GitHub main')
    parser.add_argument('--old-distribution', default=OLD_DISTRIBUTION,
                        help='Distribution commit whose bootstrap installs the old Core')
    parser.add_argument('--old-core', default=OLD_CORE, help='Core release that bootstrap installs')
    parser.add_argument('--old-has-discovery', default='yes', choices=('yes', 'no'),
                        help='whether the old Distribution commit already contains update discovery')
    options = parser.parse_args(argv)
    old_distribution, old_core = options.old_distribution, options.old_core
    source = Path(__file__).resolve().parents[2]
    base = Path(tempfile.mkdtemp(prefix='av-discovery-'))
    # Reuse the acceptance harness's existing isolated host roots so personal
    # skill discovery and Git configuration never reach a developer's home.
    sys.path.insert(0, str(source / 'src'))
    from profile_acceptance import configure_profile_environment, published_core_promotions
    if options.source_mirror:
        published = json.loads((source / 'src/aiverse_distribution/catalog/core_promotions.json').read_text())
        official = build_mirror(source, base)
    else:
        published = published_core_promotions()
        official = REPOSITORY
    NEW_CORE = published["current_release"]
    configure_profile_environment(base, 'core')
    old = base / 'old'
    old.mkdir()
    run('git', 'init', cwd=old)
    run('git', 'remote', 'add', 'origin', REPOSITORY, cwd=old)
    run('git', 'fetch', '--depth=1', 'origin', old_distribution, cwd=old)
    run('git', '-c', 'core.autocrlf=false', 'checkout', '--detach', 'FETCH_HEAD', cwd=old)
    member, stack = base / 'member', base / 's'
    # Use the canonical Python bootstrap stage with the already-qualified host
    # Python; platform wrappers prepare this same stage when Python is absent.
    run(sys.executable, old / 'scripts/project-bootstrap.py', '--project', member, '--stack', stack)
    marker = json.loads((stack / 'project.json').read_text())
    python, launcher = marker['python'], marker['launcher']

    def command(*arguments, installed_only=False):
        # `installed_only` runs the historical updater exactly as installed; every
        # other call goes through discovery, against the mirror when requested.
        if mirrored[0] and not installed_only:
            argv = [python, launcher, '--exec', python, '-I', '-B', '-c', MIRROR_RUNNER, official, *arguments, '--json']
        else:
            argv = [python, launcher, *arguments, '--json']
        return json.loads(run(*argv, capture=True))

    mirrored = [False]
    before = command('status', installed_only=True)
    assert before['release_set_id'] == old_core and before['state'] == 'ready'
    if options.old_has_discovery == 'yes':
        mirrored[0] = options.source_mirror
        original_plan = command('update', '--plan')
        assert original_plan['from'] == old_core and original_plan['to'] == NEW_CORE
        assert original_plan['noop'] is False
    else:
        # A historical updater without discovery only knows its own catalog and
        # cannot be asked to plan past it; the fixture below performs the one-time
        # tooling refresh that INSTALL.md documents for such installations.
        pass
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
    mirrored[0] = options.source_mirror
    preview = command('update', '--plan')
    assert preview['from'] == old_core and preview['to'] == NEW_CORE and not preview['noop']
    hops = expected_hops(old_core, NEW_CORE)
    assert [hop['to'] for hop in preview.get('transition_path', [])] == (hops if len(hops) > 1 else []), preview
    assert not pointer.exists()
    assert (home / 'locks/current.json').read_bytes() == receipt_before
    applied = command('update')
    assert applied['to'] == NEW_CORE and applied.get('applied') is True
    assert [hop['to'] for hop in applied.get('transition_path', [])] == (hops if len(hops) > 1 else [])
    after = command('status')
    assert after['release_set_id'] == NEW_CORE and after['state'] == 'ready'
    assert all(c['state'] == 'ready' for c in after['components'].values())
    assert command('doctor')['ok'] is True
    assert command('update')['noop'] is True
    assert all((member / path).read_bytes() == content for path, content in payload.items())
    selected = json.loads(pointer.read_text())
    assert len(selected['revision']) == 40 and selected['repository'] == official
    # Offline transport must refuse a latest-release claim, while cached local
    # status/doctor remain usable. Only the network boundary is doubled.
    offline = MIRROR_PATCH + """
def git(*args, **kwargs):
    if args[0]=='ls-remote': raise d.DiscoveryError('Latest-release status is unknown: offline')
    return _mirror_git(*args, **kwargs)
with patch.object(d, 'OFFICIAL_REPOSITORY', sys.argv[1]), patch.object(d, '_git', side_effect=git):
    assert entrypoint.main(['update','--json'])==2
    assert entrypoint.main(['status','--json'])==0
    assert entrypoint.main(['doctor','--json'])==0
"""
    run(python, launcher, '--exec', python, '-I', '-B', '-c', offline, official)
    report = {'old_core': old_core, 'hops': hops, 'source': 'checkout-mirror' if options.source_mirror else 'published-main', 'discovered_core': after['release_set_id'],
              'selected_snapshot': selected['revision'], 'preview_preserved_receipt': True,
              'member_files_preserved': len(payload), 'all_components_ready': True,
              'doctor': True, 'repeat_noop': True, 'offline_refusal_and_local_health': True,
              'fixture_root': str(base)}
    (base / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
