import unittest
from unittest.mock import patch

from aiverse_distribution import entrypoint


class UpdateDiscoveryTests(unittest.TestCase):
    def test_installed_entrypoint_uses_discovery_before_local_catalog(self):
        with patch('aiverse_distribution.update_discovery.route', return_value=17), patch(
            'aiverse_distribution.cli.main', return_value=0
        ):
            self.assertEqual(entrypoint.main(['update', '--plan', '--json']), 17)

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from aiverse_distribution import update_discovery as discovery
from aiverse_distribution.project_layout import ProjectLayout
from aiverse_distribution.release_catalog import Catalog
from aiverse_distribution.state import StateStore


def git(directory, *args):
    result = subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=directory,
                            text=True, capture_output=True, check=True)
    return result.stdout.strip()


class BoundDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.source = Path(cls.shared.name) / 'source'
        cls.source.mkdir()
        repository = Path(__file__).resolve().parents[1]
        shutil.copytree(repository / 'src', cls.source / 'src',
                        ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
        shutil.copyfile(repository / 'pyproject.toml', cls.source / 'pyproject.toml')
        git(cls.source, 'init')
        git(cls.source, 'add', '.')
        git(cls.source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'fixture')
        cls.revision = git(cls.source, 'rev-parse', 'HEAD')

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.layout = ProjectLayout.resolve(root / 'member', root / 'stack')
        self.layout.project.mkdir()
        (self.layout.project / 'AGENTS.md').write_text('member fixture')
        self.home = self.layout.distribution_home
        self.state = StateStore(self.home)
        release = Catalog().resolve('core')
        self.lock = {'profile': 'core', 'root': str(self.layout.project),
                     'release_set_id': release.id,
                     'components': {c.id: {'revision': c.revision} for c in release.components}}
        self.state.current_path.write_text(json.dumps(self.lock))
        self.layout.receipt.write_text(json.dumps({'schema_version': 1,
            'project': str(self.layout.project), 'stack': str(self.layout.stack), 'phase': 'installed'}))
        self.environment = patch.dict(os.environ, {'AIVERSE_DISTRIBUTION_HOME': str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        directory = self.home / 'updater'
        directory.mkdir()
        self.snapshot = directory / self.revision
        git(directory, 'clone', '--no-hardlinks', str(self.source), str(self.snapshot))
        git(self.snapshot, 'remote', 'set-url', 'origin', discovery.OFFICIAL_REPOSITORY)
        self.pointer = directory / 'active.json'

    def selected(self):
        return json.loads(self.pointer.read_text())['revision']

    def test_default_update_selects_verified_new_tooling_before_public_handoff(self):
        def dispatch(command):
            self.assertEqual(self.selected(), self.revision)
            self.assertIn(str(self.snapshot / 'src'), command)
            self.assertEqual(command[-2:], ['update', '--json'])
            return 0
        with patch.object(discovery, 'acquire_snapshot', return_value=(self.snapshot, self.revision)) as acquire, patch.object(
            discovery, '_dispatch', side_effect=dispatch):
            self.assertEqual(discovery.route(['update', '--json']), 0)
        acquire.assert_called_once_with(self.home)
        self.assertEqual(json.loads(self.state.current_path.read_text()), self.lock)

    def test_preview_does_not_select_tools_or_change_owner_receipts(self):
        before = (self.state.current_path.read_bytes(), self.layout.receipt.read_bytes())
        with patch.object(discovery, 'acquire_snapshot', return_value=(self.snapshot, self.revision)), patch.object(
            discovery, '_dispatch', return_value=0):
            self.assertEqual(discovery.route(['update', '--plan', '--json']), 0)
        self.assertFalse(self.pointer.exists())
        self.assertEqual(before, (self.state.current_path.read_bytes(), self.layout.receipt.read_bytes()))

    def test_failed_check_never_claims_current_or_changes_selection(self):
        with patch.object(discovery, 'acquire_snapshot', side_effect=discovery.DiscoveryError('Latest-release status is unknown')):
            with self.assertRaisesRegex(discovery.DiscoveryError, 'unknown'):
                discovery.route(['update'])
        self.assertFalse(self.pointer.exists())

    def test_selected_doctor_is_offline_and_no_discovery_recursion(self):
        discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        with patch.object(discovery, 'acquire_snapshot', side_effect=AssertionError('network')), patch.object(
            discovery, '_dispatch', return_value=0) as dispatch:
            self.assertEqual(discovery.route(['doctor', '--json']), 0)
            self.assertIn('_local_main', dispatch.call_args.args[0][4])

    def test_explicit_target_uses_existing_selected_catalog_without_network(self):
        discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        with patch.object(discovery, 'acquire_snapshot', side_effect=AssertionError('network')), patch.object(
            discovery, '_dispatch', return_value=0):
            self.assertEqual(discovery.route(['update', '--to', self.lock['release_set_id']]), 0)

    def test_source_edit_is_refused_even_when_git_marks_file_assume_unchanged(self):
        file = self.snapshot / 'src/aiverse_distribution/entrypoint.py'
        git(self.snapshot, 'update-index', '--assume-unchanged', str(file))
        file.write_text(file.read_text() + '\n# changed\n')
        with self.assertRaisesRegex(discovery.DiscoveryError, 'modified'):
            discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        self.assertFalse(self.pointer.exists())

    def test_untracked_import_source_is_refused(self):
        (self.snapshot / 'src/evil.py').write_text('raise RuntimeError()')
        with self.assertRaisesRegex(discovery.DiscoveryError, 'unrecognized'):
            discovery.verify_snapshot(self.snapshot, self.revision)

    def test_symlink_import_source_is_refused(self):
        file = self.snapshot / 'src/aiverse_distribution/entrypoint.py'
        outside = Path(self.temporary.name) / 'external.py'
        outside.write_bytes(file.read_bytes())
        file.unlink()
        try:
            file.symlink_to(outside)
        except OSError:
            self.skipTest('Host does not grant symlink creation')
        with self.assertRaisesRegex(discovery.DiscoveryError, 'symlink'):
            discovery.verify_snapshot(self.snapshot, self.revision)

    def test_source_origin_mismatch_is_refused(self):
        git(self.snapshot, 'remote', 'set-url', 'origin', 'https://example.invalid/wrong.git')
        with self.assertRaisesRegex(discovery.DiscoveryError, 'identity'):
            discovery.verify_snapshot(self.snapshot, self.revision)

    def test_incompatible_installed_receipt_preserves_old_selection(self):
        discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        previous = self.pointer.read_bytes()
        self.lock['components']['ai-verse-brain']['revision'] = '0' * 40
        self.state.current_path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(discovery.DiscoveryError, 'installed Core'):
            discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        self.assertEqual(self.pointer.read_bytes(), previous)

    def test_wrong_project_receipt_never_discovers(self):
        marker = json.loads(self.layout.receipt.read_text())
        marker['project'] = str(Path(self.temporary.name) / 'someone-else')
        self.layout.receipt.write_text(json.dumps(marker))
        with patch.object(discovery, 'acquire_snapshot') as acquire:
            with self.assertRaises(RuntimeError):
                discovery.route(['update'])
        acquire.assert_not_called()

    def test_interrupted_core_handoff_keeps_selected_tools_for_local_recovery(self):
        with patch.object(discovery, 'acquire_snapshot', return_value=(self.snapshot, self.revision)), patch.object(
            discovery, '_dispatch', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                discovery.route(['update'])
        self.assertEqual(self.selected(), self.revision)
        with patch.object(discovery, 'acquire_snapshot', side_effect=AssertionError('network')), patch.object(
            discovery, '_dispatch', return_value=0):
            self.assertEqual(discovery.route(['restore']), 0)

    def test_cached_acquisition_resolves_remote_commit_once_and_verifies_bytes(self):
        original = discovery._git
        observed = []
        def network(*args, **kwargs):
            if args[0] == 'ls-remote':
                observed.append(args)
                return self.revision + '\trefs/heads/main'
            return original(*args, **kwargs)
        with patch.object(discovery, '_git', side_effect=network):
            self.assertEqual(discovery.acquire_snapshot(self.home), (self.snapshot, self.revision))
        self.assertEqual(len(observed), 1)

    def test_unsupported_protocol_or_dependencies_are_not_executed(self):
        file = self.snapshot / 'pyproject.toml'
        file.write_text(file.read_text().replace('protocol = 1', 'protocol = 2'))
        git(self.snapshot, 'add', 'pyproject.toml')
        git(self.snapshot, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'new interface')
        revision = git(self.snapshot, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(discovery.DiscoveryError, 'newer handoff'):
            discovery.verify_snapshot(self.snapshot, revision)

    def test_network_timeout_is_actionable_and_preserves_old_tools(self):
        with patch.object(discovery.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 45)):
            with self.assertRaisesRegex(discovery.DiscoveryError, 'retry when online'):
                discovery.acquire_snapshot(self.home)
        self.assertFalse(self.pointer.exists())

    def test_selected_source_corruption_blocks_offline_execution(self):
        discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        (self.snapshot / 'src/aiverse_distribution/entrypoint.py').write_text('corrupted')
        with patch.object(discovery, '_dispatch') as dispatch:
            with self.assertRaisesRegex(discovery.DiscoveryError, 'modified'):
                discovery.route(['doctor'])
        dispatch.assert_not_called()

    def test_failed_update_status_propagates_without_false_success(self):
        with patch.object(discovery, 'acquire_snapshot', return_value=(self.snapshot, self.revision)), patch.object(
            discovery, '_dispatch', return_value=2):
            self.assertEqual(discovery.route(['update']), 2)
        self.assertEqual(self.selected(), self.revision)

    def test_metadata_only_other_component_change_is_rejected_not_mislabelled_current(self):
        self.lock['components']['ai-verse-memory']['revision'] = 'a' * 40
        self.state.current_path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(discovery.DiscoveryError, 'installed Core'):
            discovery.activate_snapshot(self.home, self.snapshot, self.revision)
        self.assertFalse(self.pointer.exists())

    def test_selection_waits_for_existing_lifecycle_lock(self):
        import threading
        import time
        started = threading.Event()
        errors = []
        def select():
            started.set()
            try:
                discovery.activate_snapshot(self.home, self.snapshot, self.revision)
            except Exception as exc:
                errors.append(exc)
        with self.state.lifecycle_transaction():
            worker = threading.Thread(target=select)
            worker.start()
            self.assertTrue(started.wait(2))
            time.sleep(0.1)
            self.assertFalse(self.pointer.exists())
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.selected(), self.revision)

    def test_fresh_bootstrap_setup_keeps_its_existing_unfinished_install_path(self):
        marker = json.loads(self.layout.receipt.read_text())
        marker['phase'] = 'installing'
        self.layout.receipt.write_text(json.dumps(marker))
        with patch.object(discovery, 'acquire_snapshot') as acquire:
            self.assertIsNone(discovery.route(['setup', '--json']))
        acquire.assert_not_called()

    def test_git_replace_cannot_substitute_another_tree_for_official_commit(self):
        file = self.snapshot / 'src/aiverse_distribution/entrypoint.py'
        file.write_text(file.read_text() + '\n# replacement tree\n')
        git(self.snapshot, 'add', '.')
        git(self.snapshot, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'replacement')
        replacement = git(self.snapshot, 'rev-parse', 'HEAD')
        git(self.snapshot, 'replace', self.revision, replacement)
        git(self.snapshot, 'update-ref', 'HEAD', self.revision)
        with self.assertRaisesRegex(discovery.DiscoveryError, 'modified'):
            discovery.verify_snapshot(self.snapshot, self.revision)
