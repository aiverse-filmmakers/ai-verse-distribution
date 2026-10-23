"""Installed public-helper acceptance with exact small registry package fixtures."""
import json
import subprocess
from pathlib import Path


def verify_tool_placement(root: Path):
    files = [root / name for name in ('package.json', 'package-lock.json', 'pyproject.toml', 'requirements.txt')]
    before = {str(p): p.read_bytes() if p.exists() else None for p in files}
    command = ['node', str(root / 'scripts/personal-tool.mjs')]
    for runtime in ('node', 'python'):
        args = ['--root', str(root), '--scope', 'operator', '--name', 'placement-acceptance-' + runtime, '--runtime', runtime]
        preview = subprocess.run(command + ['init'] + args, text=True, capture_output=True, check=True)
        assert json.loads(preview.stdout)['applied'] is False
        subprocess.run(command + ['init'] + args + ['--apply'], check=True)
        subprocess.run(command + ['check'] + args, check=True)
        package = 'is-number@7.0.0' if runtime == 'node' else 'idna==3.10'
        dispatch = subprocess.run(command + ['install'] + args + ['--package', package], text=True, capture_output=True, check=True)
        assert json.loads(dispatch.stdout)['applied'] is False
        subprocess.run(command + ['install'] + args + ['--package', package, '--apply'], check=True)
        directory = root / 'apps' / ('placement-acceptance-' + runtime)
        if runtime == 'node':
            assert (directory / 'node_modules/is-number/package.json').is_file()
        else:
            assert (directory / '.venv/pyvenv.cfg').is_file()
        refused = subprocess.run(command + ['install'] + args + ['--package', '--prefix=/tmp'], capture_output=True)
        assert refused.returncode != 0
    assert before == {str(p): p.read_bytes() if p.exists() else None for p in files}
    assert subprocess.run(['git', '-C', str(root), 'check-ignore', '--quiet', 'apps/placement-acceptance-node/package.json']).returncode == 0
    return {'node': 'pass', 'python': 'pass', 'unsafe_package_argument': 'refused', 'core_manifests': 'unchanged', 'dependency_installation': 'verified', 'tool_execution': False}
