"""Verified project-local handoff to the existing official Distribution updater.

The installed transport remains available. Selected snapshots supply one coherent
catalog/locks/engine for later local doctor and recovery, without network access.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib

from .project_layout import ProjectLayout
from .release_catalog import DistributionError
from .state import StateStore

OFFICIAL_REPOSITORY = 'https://github.com/aiverse-filmmakers/ai-verse-distribution.git'
SHA = re.compile(r'^[0-9a-f]{40}$')
COMMANDS = {'update', 'status', 'doctor', 'upgrade', 'restore', 'setup', 'open',
            'rollback', 'component', 'onboard', 'releases'}


class DiscoveryError(DistributionError):
    code = 'UPDATE_DISCOVERY_FAILED'


def _git(*arguments: str, cwd: Path | None = None, timeout: int = 45) -> str:
    argv = ['git', '-c', 'core.autocrlf=false', '-c', f'core.hooksPath={os.devnull}',
            '-c', 'protocol.file.allow=never', *arguments]
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1',
                   'GIT_NO_REPLACE_OBJECTS': '1'}
    try:
        result = subprocess.run(argv, cwd=cwd, env=environment, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoveryError('Could not check or prepare the latest official updater. '
                             'Your current tools and files are preserved; retry when online.') from exc
    if result.returncode:
        # Do not echo credentials, user Git configuration or remote diagnostics.
        raise DiscoveryError('Could not verify the official updater source. '
                             'Latest-release status is unknown; existing local doctor and recovery remain available.')
    return result.stdout.strip()


def _contained(home: Path, target: Path) -> Path:
    """Controlled paths may not redirect through symlinks or escape the receipt home."""
    try:
        parts = target.relative_to(home).parts
    except ValueError as exc:
        raise DiscoveryError('Updater path escapes its private tool stack') from exc
    current = home
    for part in parts:
        current /= part
        if current.is_symlink():
            raise DiscoveryError('Updater path contains a symlink; preserve it for review')
    if not target.resolve().is_relative_to(home.resolve()):
        raise DiscoveryError('Updater path escapes its private tool stack')
    return target


def _binding() -> tuple[Path, dict] | None:
    configured = os.environ.get('AIVERSE_DISTRIBUTION_HOME')
    if not configured:
        return None  # Non-project advanced CLI keeps its existing explicit catalog.
    home = Path(configured).expanduser().resolve()
    marker_path = home.parent / 'project.json'
    if not marker_path.exists():
        return None
    if marker_path.is_symlink():
        raise DiscoveryError('Project tooling receipt is a symlink; update stopped safely')
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    if not isinstance(marker, dict) or not isinstance(marker.get('project'), str):
        raise DiscoveryError('Project tooling receipt is invalid')
    layout = ProjectLayout.resolve(Path(marker['project']), home.parent)
    layout.inspect()
    if layout.distribution_home != home:
        raise DiscoveryError('Project tooling is bound to another installation')
    if marker.get('phase') != 'installed':
        # Fresh bootstrap calls owner setup before its final receipt commit.
        # That established install/resume path must finish before discovery applies.
        return None
    lock = json.loads(_contained(home, home / 'locks/current.json').read_text(encoding='utf-8'))
    if lock.get('root') != str(layout.project) or lock.get('profile') != 'core':
        raise DiscoveryError('Updater does not match this installed Core project')
    return home, lock


def verify_snapshot(snapshot: Path, revision: str) -> str:
    """Verify executable/catalog source bytes against the exact official Git tree."""
    if not SHA.fullmatch(revision):
        raise DiscoveryError('Invalid updater revision')
    if not (snapshot / '.git').is_dir() or (snapshot / '.git').is_symlink():
        raise DiscoveryError('Updater Git metadata is redirected or absent')
    if (_git('remote', 'get-url', 'origin', cwd=snapshot) != OFFICIAL_REPOSITORY
            or _git('rev-parse', 'HEAD', cwd=snapshot) != revision):
        raise DiscoveryError('Updater source identity does not match its receipt')
    _git('fsck', '--strict', '--no-dangling', cwd=snapshot)
    if snapshot.joinpath('.git').is_symlink():
        raise DiscoveryError('Updater Git metadata is redirected')
    expected = set()
    tree = _git('ls-tree', '-rz', '--full-tree', 'HEAD', cwd=snapshot)
    for entry in tree.split('\0'):
        if not entry:
            continue
        metadata, name = entry.split('\t', 1)
        mode, kind, digest = metadata.split()
        if name != 'pyproject.toml' and not name.startswith('src/'):
            continue
        if mode not in {'100644', '100755'} or kind != 'blob':
            raise DiscoveryError('Updater source contains an unsupported filesystem entry')
        file = _contained(snapshot, snapshot / name)
        if not file.is_file():
            raise DiscoveryError('Updater source is incomplete')
        content = file.read_bytes()
        blob = b'blob ' + str(len(content)).encode() + b'\0' + content
        if hashlib.sha1(blob).hexdigest() != digest:
            raise DiscoveryError('Updater source was modified; preserve it for review')
        expected.add(name)
    # Do not allow ignored/untracked modules to enter the import path either.
    actual = {p.relative_to(snapshot).as_posix() for p in (snapshot / 'src').rglob('*')
              if p.is_file() or p.is_symlink()}
    if actual != {name for name in expected if name.startswith('src/')}:
        raise DiscoveryError('Updater source contains unrecognized files')
    project = tomllib.loads((snapshot / 'pyproject.toml').read_text(encoding='utf-8'))
    interface = project.get('tool', {}).get('aiverse', {}).get('distribution-update', {})
    if (interface.get('protocol') != 1 or isinstance(interface.get('protocol'), bool)
            or interface.get('entrypoint') not in {'main', '_local_main'}
            or project.get('project', {}).get('dependencies') != []
            or project.get('project', {}).get('requires-python') != '>=3.11'):
        raise DiscoveryError('Official updater requires a newer handoff interface or dependencies. '
                             'Use the canonical bootstrap to refresh tooling; no member files were changed.')
    functions = {node.name for node in ast.parse(
        (snapshot / 'src/aiverse_distribution/entrypoint.py').read_text(encoding='utf-8')).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if interface['entrypoint'] not in functions or (interface['entrypoint'] == 'main' and '_local_main' in functions):
        raise DiscoveryError('Updater handoff would recurse or is unavailable; use canonical bootstrap guidance')
    return interface['entrypoint']


def acquire_snapshot(home: Path) -> tuple[Path, str]:
    advertised = _git('ls-remote', OFFICIAL_REPOSITORY, 'refs/heads/main').split()
    if len(advertised) != 2 or not SHA.fullmatch(advertised[0]) or advertised[1] != 'refs/heads/main':
        raise DiscoveryError('Official updater did not advertise one valid main revision')
    revision = advertised[0]
    directory = _contained(home, home / 'updater')
    directory.mkdir(exist_ok=True)
    snapshot = _contained(home, directory / revision)
    if not snapshot.exists():
        # Unique staging means interrupted/concurrent downloads cannot replace a
        # complete snapshot. A crash leaves only disposable unselected staging.
        with tempfile.TemporaryDirectory(prefix='stage-', dir=directory) as temporary:
            stage = Path(temporary) / 'source'
            stage.mkdir()
            _git('init', cwd=stage)
            _git('remote', 'add', 'origin', OFFICIAL_REPOSITORY, cwd=stage)
            _git('fetch', '--depth=1', 'origin', revision, cwd=stage, timeout=120)
            _git('checkout', '--detach', 'FETCH_HEAD', cwd=stage)
            verify_snapshot(stage, revision)
            try:
                stage.rename(snapshot)
            except OSError:
                if not snapshot.exists():
                    raise
    verify_snapshot(snapshot, revision)
    return snapshot, revision


def _selected(home: Path) -> tuple[Path, str] | None:
    pointer = _contained(home, home / 'updater/active.json')
    if not pointer.exists():
        return None
    record = json.loads(pointer.read_text(encoding='utf-8'))
    if (not isinstance(record, dict) or record.get('schema_version') != 1
            or record.get('repository') != OFFICIAL_REPOSITORY
            or not isinstance(record.get('revision'), str) or not SHA.fullmatch(record['revision'])):
        raise DiscoveryError('Selected updater receipt is invalid; use canonical bootstrap recovery')
    snapshot = _contained(home, home / 'updater' / record['revision'])
    verify_snapshot(snapshot, record['revision'])
    return snapshot, record['revision']


def _source_command(snapshot: Path, program: str, arguments: list[str]) -> list[str]:
    return [sys.executable, '-I', '-B', '-c',
            'import sys; sys.path.insert(0, sys.argv.pop(1)); ' + program,
            str(snapshot / 'src'), *arguments]


def activate_snapshot(home: Path, snapshot: Path, revision: str) -> None:
    state = StateStore(home)
    with state.lifecycle_transaction():
        # Source/catalog must still understand the actual installed receipt after
        # any concurrent lifecycle transaction, before the selector can advance.
        _, lock = _binding() or (None, None)
        if lock is None:
            raise DiscoveryError('Project binding disappeared before updater selection')
        verify_snapshot(snapshot, revision)
        try:
            probe = subprocess.run(_source_command(snapshot,
                'import json; from aiverse_distribution.release_catalog import Catalog; '
                'c=Catalog(); r=c.get_release(sys.argv[1], require_released=True); '
                'expected=json.loads(sys.argv[2]); '
                'raise SystemExit(0 if {x.id:x.revision for x in r.components} == expected else 3)',
                [lock['release_set_id'], json.dumps({k: v['revision'] for k, v in lock['components'].items()})]),
                capture_output=True, text=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            raise DiscoveryError('Updater compatibility check timed out; previous tools are preserved') from exc
        if probe.returncode:
            raise DiscoveryError('The discovered updater cannot verify the installed Core. '
                                 'Existing tools are preserved; use canonical bootstrap guidance.')
        state._atomic_json(_contained(home, home / 'updater/active.json'), {
            'schema_version': 1, 'repository': OFFICIAL_REPOSITORY, 'revision': revision,
        })


def route(arguments: list[str]) -> int | None:
    if not arguments or arguments[0] not in COMMANDS or any(x in arguments for x in ('-h', '--help')):
        return None
    bound = _binding()
    if bound is None:
        return None
    home, _ = bound
    default_update = arguments[0] == 'update' and not any(
        x in {'--to', '--release-set'} or x.startswith(('--to=', '--release-set=')) for x in arguments)
    if default_update:
        snapshot, revision = acquire_snapshot(home)
        if '--plan' not in arguments:
            activate_snapshot(home, snapshot, revision)
    else:
        selected = _selected(home)
        if selected is None:
            return None
        snapshot, revision = selected
    method = verify_snapshot(snapshot, revision)
    # Snapshot code calls the local lifecycle directly: no discovery recursion,
    # pip overwrite, launcher rewrite or loss of the installed fallback transport.
    command = _source_command(snapshot,
        f'from aiverse_distribution.entrypoint import {method} as dispatch; '
        'raise SystemExit(dispatch(sys.argv[1:]))', arguments)
    return _dispatch(command)


def _dispatch(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode
