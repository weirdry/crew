"""Offline release invariants; all mutations use disposable repositories/homes."""
import sys
sys.dont_write_bytecode = True

import argparse
import copy
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/release'))
import check_version
import consume
import evidence
import install
import package
import publish
import release_lib
from release_lib import (Invalid, MANIFEST, MARKER, encoded, extract_verified,
                         inventory, load_payload, read_archive, record, sha256,
                         validate_inventory)


def commit(root, message='Synthetic fixture'):
    env = os.environ | {'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                        'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True, env=env)
    subprocess.run(['git', '-C', str(root), 'commit', '-qm', message], check=True, capture_output=True, env=env)
    return package.git(root, 'rev-parse', 'HEAD').decode().strip()


class FakeGitHub:
    """Stateful synthetic remote, including a failure after an accepted mutation."""
    def __init__(self):
        self.ref = None
        self.data = None
        self.bytes = {}
        self.calls = []
        self.immutable = True
        self.fail_upload = None
        self.next_id = 10

    def tag(self, version):
        return self.ref

    def release(self, version):
        return copy.deepcopy(self.data)

    def asset_bytes(self, asset):
        return self.bytes[asset['id']]

    def request(self, path, method='GET', data=None, **kwargs):
        self.calls.append((path, method, copy.deepcopy(data)))
        if path.endswith('/git/refs'):
            assert self.ref is None
            self.ref = data['sha']
        elif path.endswith('/releases'):
            assert self.data is None
            self.data = data | {'id': 1, 'assets': [], 'immutable': False,
                                'html_url': 'https://github.com/weirdry/crew/releases/tag/' + data['tag_name']}
            return self.release('')
        elif '/assets?name=' in path:
            name = path.split('name=')[1]
            assert name not in [a['name'] for a in self.data['assets']]
            self.next_id += 1
            self.bytes[self.next_id] = data
            self.data['assets'].append({'id': self.next_id, 'name': name, 'state': 'uploaded'})
            if self.fail_upload == name:
                self.fail_upload = None
                raise Invalid('synthetic lost upload response')
        elif method == 'PATCH':
            self.data.update(data)
            if data.get('draft') is False:
                self.data['immutable'] = self.immutable
        else:
            raise AssertionError((path, method))
        return self.release('')


class Releases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='crew-release-fixtures-')
        cls.base = Path(cls.storage.name).resolve()
        cls.repository = cls.base / 'source'
        cls.repository.mkdir()
        for path in ('VERSION', 'LICENSE', 'INSTALL.md', 'CHANGELOG.md'):
            shutil.copy2(ROOT / path, cls.repository / path)
        shutil.copytree(ROOT / 'skills', cls.repository / 'skills')
        shutil.copytree(ROOT / 'tools', cls.repository / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run(['git', 'init', '-q', str(cls.repository)], check=True)
        cls.source = commit(cls.repository)
        cls.output = cls.base / 'candidate'
        cls.manifest = package.build(cls.repository, cls.output)
        cls.archive = cls.output / ('crew-v' + cls.manifest['version'] + '.tar.gz')
        cls.checksum = sha256(cls.archive.read_bytes())
        cls.payload = cls.base / 'payload'
        extract_verified(cls.archive, cls.checksum, cls.payload)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.home = self.work / 'home'
        self.home.mkdir()
        self.args = argparse.Namespace(payload=self.payload, command='install', host='all', home=self.home,
                                       codex_root=None, claude_root=None, extra_skill_root=[], inactive=True)
        self.destination = self.home / '.agents/skills/crew'
        self.wanted = install.expected_marker(self.manifest, 'codex')
        self.api = FakeGitHub()

    def run_install(self):
        with mock.patch('pathlib.Path.cwd', return_value=self.work):
            return install.run(self.args)

    def copied_source(self):
        root = self.work / 'source'
        shutil.copytree(self.repository, root)
        return root

    def publish(self, directory=None, source=None):
        result = {'publication': 'not-attempted', 'verification': 'not-started', 'eligible': False}
        publish.publish(self.api, directory or self.output, source or self.source,
                        'https://github.com/weirdry/crew/actions/runs/123', result)
        return result

    def test_build_is_deterministic_and_complete(self):
        other = self.work / 'other'
        self.assertEqual(package.build(self.repository, other), self.manifest)
        for p in self.output.iterdir():
            self.assertEqual(p.read_bytes(), (other / p.name).read_bytes())
        self.assertEqual(self.manifest['source'], self.source)
        self.assertEqual(self.manifest['files']['skill/scripts/relay.sh']['mode'], 0o755)
        self.assertNotIn('tests/run.sh', self.manifest['files'])
        self.assertEqual(load_payload(self.payload), self.manifest)

    def test_build_rejects_dirty_source(self):
        root = self.copied_source()
        (root / 'notes.txt').write_text('uncommitted')
        with self.assertRaisesRegex(Invalid, 'clean'):
            package.build(root, self.work / 'out')
        self.assertFalse((self.work / 'out').exists())

    def test_skill_inventory_requires_explicit_decision(self):
        root = self.copied_source()
        (root / 'skills/crew/session.json').write_text('{}')
        commit(root)
        with self.assertRaisesRegex(Invalid, 'packaging decision'):
            package.build(root, self.work / 'out')

    def test_source_symlink_refused(self):
        root = self.copied_source()
        script = root / 'skills/crew/scripts/relay.sh'
        script.unlink()
        script.symlink_to('artifact-done.sh')
        commit(root)
        with self.assertRaisesRegex(Invalid, 'unsupported source'):
            package.build(root, self.work / 'out')

    def test_changelog_and_version_required(self):
        root = self.copied_source()
        (root / 'VERSION').write_text('1.2.3\n')
        commit(root)
        with self.assertRaisesRegex(Invalid, 'CHANGELOG'):
            package.build(root, self.work / 'out')

    def test_unsafe_archive_entries_rejected_before_extraction(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                           ('.', tarfile.REGTYPE), ('linked', tarfile.SYMTYPE),
                           ('hard', tarfile.LNKTYPE)]:
            with self.subTest(name=name):
                bad = self.work / 'bad.tar.gz'
                with tarfile.open(bad, 'w:gz') as tar:
                    entry = tarfile.TarInfo(name)
                    entry.mode, entry.type = 0o644, kind
                    tar.addfile(entry, io.BytesIO(b''))
                target = self.work / 'extracted'
                with self.assertRaises(Invalid):
                    extract_verified(bad, sha256(bad.read_bytes()), target)
                self.assertFalse(target.exists())

    def test_archive_inventory_and_modes_enforced(self):
        for change in ('duplicate', 'missing', 'modified', 'mode'):
            with self.subTest(change=change):
                bad = self.work / 'bad.tar.gz'
                with tarfile.open(self.archive) as original, tarfile.open(bad, 'w:gz') as dest:
                    for entry in original:
                        data = original.extractfile(entry).read()
                        if entry.name == 'skill/SKILL.md':
                            if change == 'missing':
                                continue
                            if change == 'modified':
                                data += b'drift'
                                entry.size = len(data)
                            if change == 'mode':
                                entry.mode = 0o755
                        dest.addfile(entry, io.BytesIO(data))
                        if change == 'duplicate' and entry.name == MANIFEST:
                            dest.addfile(entry, io.BytesIO(data))
                with self.assertRaises(Invalid):
                    read_archive(bad, sha256(bad.read_bytes()))
        with self.assertRaisesRegex(Invalid, 'checksum'):
            read_archive(self.archive, '0' * 64)

    def test_case_and_parent_collisions_rejected(self):
        for paths in (('A', 'a'), ('A', 'a/b'), ('x', 'x/b'), ('A/x', 'a/y')):
            with self.subTest(paths=paths), self.assertRaises(Invalid):
                validate_inventory({p: record(b'x', 0o644) for p in paths})

    def test_expansion_is_bounded_before_tar_metadata_parsing(self):
        archive = self.work / 'large-metadata.tar.gz'
        archive.write_bytes(gzip.compress(b'x' * 2048))
        with mock.patch.object(release_lib, 'MAX_BYTES', 1024), self.assertRaisesRegex(Invalid, 'expansion'):
            read_archive(archive, sha256(archive.read_bytes()))

    def test_both_hosts_and_repeat_are_current_without_writes(self):
        result = self.run_install()
        self.assertEqual([r['action'] for r in result], ['installed', 'installed'])
        before = {str(p): p.stat().st_mtime_ns for p in self.home.rglob('*')}
        self.args.inactive = False
        result = self.run_install()
        self.assertEqual([r['status'] for r in result], ['current', 'current'])
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.home.rglob('*')})
        self.args.command = 'check'
        self.assertEqual([r['status'] for r in self.run_install()], ['current', 'current'])

    def test_check_and_inactive_refusal_do_not_create_roots(self):
        self.args.command = 'check'
        self.assertEqual([r['status'] for r in self.run_install()], ['missing', 'missing'])
        self.assertEqual(list(self.home.iterdir()), [])
        self.args.command, self.args.inactive = 'install', False
        self.assertEqual([r['status'] for r in self.run_install()], ['error', 'error'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unmanaged_host_preserved_other_host_succeeds(self):
        self.destination.mkdir(parents=True)
        (self.destination / 'mine').write_text('keep')
        result = self.run_install()
        self.assertEqual([r['status'] for r in result], ['conflicting', 'current'])
        self.assertEqual((self.destination / 'mine').read_text(), 'keep')

    def test_modified_files_modes_and_empty_directories_preserved(self):
        for change in ('content', 'mode', 'extra', 'empty', 'missing'):
            with self.subTest(change=change):
                root = self.work / change
                install.replace_managed(self.payload, root, self.wanted)
                file = root / 'SKILL.md'
                if change == 'content': file.write_text('user modification')
                if change == 'mode': file.chmod(0o755)
                if change == 'extra': (root / 'mine').write_text('keep')
                if change == 'empty': (root / 'empty').mkdir()
                if change == 'missing': file.unlink()
                self.assertEqual(install.inspect(root, self.wanted)['status'], 'modified')
                with self.assertRaises(Invalid):
                    install.replace_managed(self.payload, root, self.wanted)

    def test_development_symlink_and_linked_parent_preserved(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to(self.payload / 'skill', target_is_directory=True)
        self.assertEqual(self.run_install()[0]['status'], 'conflicting')
        self.assertTrue(self.destination.is_symlink())
        linked = self.work / 'linked'
        linked.symlink_to(self.destination.parent, target_is_directory=True)
        self.args.codex_root = linked
        self.assertEqual(self.run_install()[0]['status'], 'conflicting')

    def test_root_aliases_remain_current_for_default_selected_and_extra_roots(self):
        for host, folder in [('codex', '.agents'), ('claude', '.claude')]:
            with self.subTest(host=host):
                actual = self.work / ('dotfiles-' + host)
                actual.mkdir()
                normal = self.home / folder
                normal.symlink_to(actual, target_is_directory=True)
                self.args.host, self.args.inactive = host, True
                result = self.run_install()[0]
                self.assertEqual(result['action'], 'installed')
                self.assertEqual(result['destination'], str(actual / 'skills/crew'))
                alias = self.work / ('alias-' + host)
                alias.symlink_to(actual / 'skills', target_is_directory=True)
                self.args.extra_skill_root = [normal / 'skills', alias, actual / 'skills']
                before = {str(p): (p.lstat().st_mode, p.lstat().st_mtime_ns) for p in actual.rglob('*')}
                self.args.inactive = False
                for selected in [None, actual / 'skills', alias]:
                    setattr(self.args, host + '_root', selected)
                    for command in ['check', 'install']:
                        self.args.command = command
                        result = self.run_install()[0]
                        self.assertEqual(result['status'], 'current')
                        self.assertEqual(result['destination'], str(actual / 'skills/crew'))
                self.assertEqual(before, {str(p): (p.lstat().st_mode, p.lstat().st_mtime_ns) for p in actual.rglob('*')})
                self.assertEqual(normal.readlink(), actual)
                self.assertEqual(alias.readlink(), actual / 'skills')
                self.args.extra_skill_root = []

    def test_selected_temporary_root_uses_its_canonical_path(self):
        # /tmp is a symlink on macOS, a regular directory on Linux.
        with tempfile.TemporaryDirectory(prefix='crew-root-', dir='/tmp') as temporary:
            self.args.host = 'codex'
            self.args.codex_root = Path(temporary) / 'new/skills'
            self.args.extra_skill_root = [self.args.codex_root.resolve()]
            result = self.run_install()[0]
            self.assertEqual(result['action'], 'installed')
            self.assertEqual(result['destination'], str(self.args.codex_root.resolve() / 'crew'))
            self.args.command = 'check'
            self.assertEqual(self.run_install()[0]['status'], 'current')

    def test_separate_crew_symlink_still_counts_as_conflicting_discovery(self):
        self.args.host = 'codex'
        self.run_install()
        before = inventory(self.destination)
        other = self.work / 'other-root'
        other.mkdir()
        (other / 'crew').symlink_to(self.destination, target_is_directory=True)
        self.args.extra_skill_root = [other]
        result = self.run_install()[0]
        self.assertEqual(result['status'], 'conflicting')
        self.assertEqual(result['conflicts'], [str(other / 'crew')])
        self.assertEqual(inventory(self.destination), before)
        self.assertEqual((other / 'crew').readlink(), self.destination)

    def test_parent_changed_after_root_resolution_is_refused(self):
        selected, other = self.work / 'selected', self.work / 'other'
        selected.mkdir()
        other.mkdir()
        self.args.codex_root = selected
        with mock.patch('pathlib.Path.cwd', return_value=self.work):
            destination, conflicts = install.host_paths(self.args, 'codex')
        self.assertEqual(conflicts, [])
        selected.rmdir()
        selected.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(Invalid, 'unsafe directory'):
            install.replace_managed(self.payload, destination, self.wanted)
        self.assertEqual(list(other.iterdir()), [])

    def test_documented_extraction_and_install_preserve_modes_under_restrictive_umask(self):
        payload = self.work / 'extracted'
        payload.mkdir(mode=0o700)
        subprocess.run(['tar', '-xzpf', str(self.archive), '-C', str(payload)], check=True, umask=0o077)
        self.assertEqual(load_payload(payload), self.manifest)
        for command in ['install', 'check', 'install']:
            args = [sys.executable, '-B', str(payload / 'install.py'), command,
                    '--host', 'all', '--home', str(self.home), '--inactive']
            result = subprocess.run(args, cwd=self.work, capture_output=True, text=True, umask=0o077)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([r['status'] for r in json.loads(result.stdout)['results']], ['current', 'current'])

    def test_duplicate_legacy_custom_and_workspace_roots(self):
        roots = [self.home / '.codex/skills', self.work / 'custom', self.work / '.agents/skills']
        for root in roots:
            with self.subTest(root=root):
                (root / 'crew').mkdir(parents=True)
                self.args.extra_skill_root = [self.work / 'custom']
                result = self.run_install()[0]
                self.assertEqual(result['status'], 'conflicting')
                self.assertIn(str(root / 'crew'), result['conflicts'])
                self.assertFalse(self.destination.exists())
                (root / 'crew').rmdir()

    def test_payload_tamper_prevents_all_writes(self):
        payload = self.work / 'payload'
        shutil.copytree(self.payload, payload)
        (payload / 'skill/SKILL.md').write_text('drift')
        self.args.payload = payload
        with self.assertRaisesRegex(Invalid, 'payload content'):
            self.run_install()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_managed_version_update_and_same_version_conflict(self):
        self.run_install()
        next_marker = self.wanted | {'version': '0.1.1', 'source': 'a' * 40}
        self.assertEqual(install.inspect(self.destination, next_marker)['status'], 'stale')
        result = install.replace_managed(self.payload, self.destination, next_marker)
        self.assertEqual(result['action'], 'updated')
        self.assertEqual(install.inspect(self.destination, next_marker)['status'], 'current')
        conflict = next_marker | {'source': 'b' * 40}
        self.assertEqual(install.inspect(self.destination, conflict)['status'], 'conflicting')
        self.assertFalse((self.destination.parent / '.crew-install-pending').exists())

    def test_update_installs_new_version_and_removes_obsolete_payload_files(self):
        self.run_install()
        root = self.copied_source()
        (root / 'VERSION').write_text('0.1.1\n')
        changelog = root / 'CHANGELOG.md'
        changelog.write_text('# Changelog\n\n## 0.1.1\n\nSynthetic correction.\n\n' + changelog.read_text())
        old = next((root / 'skills/crew/templates').glob('*.md'))
        old.unlink()
        new = root / 'skills/crew/templates/synthetic.md'
        new.write_text('Synthetic updated payload\n')
        commit(root)
        output = self.work / 'updated'
        manifest = package.build(root, output)
        archive = output / 'crew-v0.1.1.tar.gz'
        payload = self.work / 'updated-payload'
        extract_verified(archive, sha256(archive.read_bytes()), payload)
        self.args.payload = payload
        self.assertEqual([r['action'] for r in self.run_install()], ['updated', 'updated'])
        self.assertFalse((self.destination / 'templates' / old.name).exists())
        self.assertEqual((self.destination / 'templates/synthetic.md').read_text(), new.read_text())
        self.assertEqual(install.inspect(self.destination, install.expected_marker(manifest, 'codex'))['status'], 'current')

    def test_after_swap_failure_keeps_previous_and_new_evidence(self):
        self.run_install()
        before = inventory(self.destination)
        original = install.inspect
        calls = 0
        def fail_once(destination, wanted):
            nonlocal calls
            calls += 1
            if calls == 4:  # After before/stage/recheck, the new directory is in place.
                return {'status': 'modified'}
            return original(destination, wanted)
        with mock.patch.object(install, 'inspect', side_effect=fail_once), self.assertRaises(Invalid):
            install.replace_managed(self.payload, self.destination, self.wanted | {'version': '0.1.1'})
        pending = self.destination.parent / '.crew-install-pending'
        self.assertEqual(inventory(pending / 'previous'), before)
        self.assertTrue(self.destination.is_dir())
        with self.assertRaisesRegex(Invalid, 'unfinished'):
            install.replace_managed(self.payload, self.destination, self.wanted)

    def test_swap_failure_restores_previous_directory(self):
        self.run_install()
        before = inventory(self.destination)
        rename = os.rename
        def fail_stage(source, target):
            if Path(source).name == 'new':
                raise OSError('synthetic replacement failure')
            return rename(source, target)
        with mock.patch.object(install.os, 'rename', side_effect=fail_stage), self.assertRaises(OSError):
            install.replace_managed(self.payload, self.destination, self.wanted | {'version': '0.1.1'})
        self.assertEqual(inventory(self.destination), before)
        self.assertFalse((self.destination.parent / '.crew-install-pending').exists())

    def test_pending_transaction_and_unsafe_lock_preserved(self):
        self.destination.parent.mkdir(parents=True)
        pending = self.destination.parent / '.crew-install-pending'
        pending.mkdir()
        (pending / 'evidence').write_text('keep')
        self.assertEqual(self.run_install()[0]['status'], 'error')
        self.assertEqual((pending / 'evidence').read_text(), 'keep')
        lock = self.destination.parent / '.crew-install.lock'
        lock.unlink()
        lock.symlink_to(pending / 'evidence')
        self.assertEqual(self.run_install()[0]['status'], 'error')
        self.assertEqual((pending / 'evidence').read_text(), 'keep')

    def test_isolated_archive_consumer_executes_packaged_helpers(self):
        work = self.work / 'consumer'
        work.mkdir()
        self.assertEqual(consume.exercise(self.archive, self.checksum, work), self.manifest)

    def test_version_change_required_only_for_release_inputs(self):
        root = self.copied_source()
        base = self.source
        (root / 'README.md').write_text('source-only documentation')
        commit(root)
        self.assertEqual(check_version.check(root, base), 'release version checked')
        (root / 'skills/crew/SKILL.md').write_text('changed input')
        commit(root)
        with self.assertRaisesRegex(Invalid, 'newer VERSION'):
            check_version.check(root, base)
        (root / 'VERSION').write_text('0.2.0\n')
        commit(root)
        self.assertEqual(check_version.check(root, base), 'release version checked')
        with self.assertRaises(subprocess.CalledProcessError):
            check_version.check(root, 'nonexistent-base')

    def test_publish_new_release_and_retry_do_not_overwrite(self):
        first = self.publish()
        self.assertEqual(first['publication'], 'published')
        self.assertTrue(first['eligible'])
        calls = len(self.api.calls)
        self.assertEqual(self.publish(), first)
        self.assertEqual(len(self.api.calls), calls)
        self.assertEqual(len(self.api.data['assets']), 3)

    def test_tag_only_and_partial_draft_resume(self):
        self.api.ref = self.source
        self.api.fail_upload = 'SHA256SUMS'
        with self.assertRaisesRegex(Invalid, 'lost upload'):
            self.publish()
        self.assertTrue(self.api.data['draft'])
        before = copy.deepcopy(self.api.bytes)
        self.assertTrue(self.publish()['eligible'])
        self.assertTrue(all(self.api.bytes[k] == v for k, v in before.items()))
        self.assertEqual(len(self.api.bytes), 3)

    def test_conflicting_draft_asset_and_tag_are_preserved(self):
        self.api.ref = 'a' * 40
        with self.assertRaisesRegex(Invalid, 'another source'):
            self.publish()
        self.assertEqual(self.api.calls, [])
        self.api.ref = self.source
        self.api.fail_upload = 'SHA256SUMS'
        with self.assertRaises(Invalid): self.publish()
        first = self.api.data['assets'][0]['id']
        self.api.bytes[first] = b'different'
        before = len(self.api.calls)
        with self.assertRaisesRegex(Invalid, 'asset conflict'): self.publish()
        self.assertEqual(len(self.api.calls), before)
        self.assertTrue(self.api.data['draft'])

    def test_empty_starter_draft_stops_until_explicit_fixture_recovery(self):
        self.api.fail_upload = 'SHA256SUMS'
        with self.assertRaises(Invalid):
            self.publish()
        asset = next(a for a in self.api.data['assets'] if a['name'] == 'SHA256SUMS')
        asset.update(state='starter', size=0)
        self.api.bytes[asset['id']] = b''
        calls, remote = len(self.api.calls), copy.deepcopy(self.api.data)
        with self.assertRaisesRegex(Invalid, 'incomplete draft upload: SHA256SUMS'):
            self.publish()
        self.assertEqual(len(self.api.calls), calls)
        self.assertEqual(self.api.data, remote)
        self.assertEqual(self.api.bytes[asset['id']], b'')
        matching = {a['id']: self.api.bytes[a['id']] for a in remote['assets'] if a['id'] != asset['id']}
        # Simulate the documented, explicitly authorized operator action in the fake only.
        self.api.data['assets'].remove(asset)
        del self.api.bytes[asset['id']]
        self.assertTrue(self.publish()['eligible'])
        self.assertTrue(all(self.api.bytes[k] == value for k, value in matching.items()))
        self.assertEqual(len(self.api.data['assets']), 3)

    def test_empty_starter_advice_does_not_apply_to_other_conflicts(self):
        self.api.bytes[99] = b''
        for draft, immutable, state, size, message in [
            (True, False, 'starter', 0, 'incomplete draft upload'),
            (True, False, 'starter', 1, 'inspect the draft conflict'),
            (True, False, 'uploaded', 0, 'inspect the draft conflict'),
            (False, True, 'starter', 0, 'use a correction version'),
            (True, True, 'starter', 0, 'use a correction version'),
        ]:
            with self.subTest(draft=draft, immutable=immutable, state=state, size=size):
                release = {'draft': draft, 'immutable': immutable,
                           'assets': [{'id': 99, 'name': 'asset', 'state': state, 'size': size}]}
                with self.assertRaisesRegex(Invalid, message):
                    publish.verify_assets(self.api, release, {'asset': b'expected'})
        self.assertEqual(self.api.calls, [])
        self.assertEqual(self.api.bytes[99], b'')

    def test_docs_only_publication_preserves_original_identity(self):
        first = self.publish()
        root = self.copied_source()
        (root / 'README.md').write_text('docs only')
        source = commit(root)
        output = self.work / 'out'
        package.build(root, output)
        before = len(self.api.calls)
        result = self.publish(output, source)
        self.assertEqual(result['publication'], 'unchanged')
        self.assertEqual(result['source'], self.source)
        self.assertEqual(result['sha256'], first['sha256'])
        self.assertFalse(result['eligible'])
        self.assertEqual(len(self.api.calls), before)

    def test_reused_version_with_changed_inputs_refused(self):
        self.publish()
        root = self.copied_source()
        (root / 'skills/crew/SKILL.md').write_text('different')
        source = commit(root)
        output = self.work / 'out'
        package.build(root, output)
        with self.assertRaisesRegex(Invalid, 'without a new version'):
            self.publish(output, source)

    def test_mutable_publication_is_reported_published_but_incomplete(self):
        self.api.immutable = False
        result = {'publication': 'not-attempted', 'eligible': False}
        with self.assertRaisesRegex(Invalid, 'not immutable'):
            publish.publish(self.api, self.output, self.source, 'https://github.com/weirdry/crew/actions/runs/123', result)
        self.assertEqual(result['publication'], 'published')
        self.assertFalse(result['eligible'])
        self.assertFalse(self.api.data['draft'])

    def test_missing_published_asset_is_not_repaired(self):
        self.publish()
        self.api.data['assets'].pop()
        before = len(self.api.calls)
        with self.assertRaises(Invalid): self.publish()
        self.assertEqual(len(self.api.calls), before)

    def test_cross_host_redirect_removes_credential(self):
        req = urllib.request.Request('https://api.github.com/assets/1', headers={'Authorization': 'Bearer synthetic'})
        redirected = publish.PublicRedirect().redirect_request(req, None, 302, 'Found', {}, 'https://objects.example.invalid/file')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(Invalid):
            publish.PublicRedirect().redirect_request(req, None, 302, 'Found', {}, 'http://objects.example.invalid/file')

    def test_publication_cli_refuses_non_main_without_network(self):
        result = self.work / 'result.json'
        process = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/release/publish.py'),
                                  '--candidate', str(self.output), '--result', str(result)],
                                 env=os.environ | {'GITHUB_REF': 'refs/heads/dev'}, capture_output=True)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(json.loads(result.read_text())['publication'], 'not-attempted')

    def test_evidence_requires_both_actual_public_downloads(self):
        publication = self.publish()
        one = {k: publication[k] for k in ('version', 'source', 'sha256')}
        one |= {'verification': 'passed', 'source_kind': 'published-download'}
        url = 'https://github.com/weirdry/crew/actions/runs/123/attempts/1'
        records = {evidence.PLATFORMS[0]: one}
        self.assertFalse(evidence.record_evidence(self.api, publication, records, url))
        self.assertIn('Verification: **incomplete**', self.api.data['body'])
        records[evidence.PLATFORMS[1]] = one
        self.assertTrue(evidence.record_evidence(self.api, publication, records, url))
        self.assertIn('Verification: **passed**', self.api.data['body'])
        self.assertEqual(self.api.data['body'].count(evidence.START), 1)
        self.assertFalse(evidence.record_evidence(self.api, publication, records, url, 'failure'))
        self.assertIn('Verification: **incomplete**', self.api.data['body'])
        records[evidence.PLATFORMS[1]] = one | {'source_kind': 'local-candidate'}
        self.assertFalse(evidence.record_evidence(self.api, publication, records, url))
        self.assertEqual(len(self.api.data['assets']), 3)


if __name__ == '__main__':
    unittest.main()
