import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('check_upstream', Path(__file__).with_name('check_upstream.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
SHA = 'a' * 40


class CheckTests(unittest.TestCase):
    def run_check(self, release=None, force=False, old_source=False, merge_type='fast-forward'):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / 'output'
            summary = root / 'summary'
            mirror_reads = 0
            def api(method, path, data=None, missing_ok=False):
                nonlocal mirror_reads
                if path == 'repos/test/visualboyadvance-m':
                    return {'fork': True, 'parent': {'full_name': check.UPSTREAM}}
                if path == f'repos/{check.UPSTREAM}/git/ref/heads/master':
                    return {'object': {'sha': SHA}}
                if path == 'repos/test/visualboyadvance-m/git/ref/heads/master':
                    mirror_reads += 1
                    return {'object': {'sha': 'b' * 40 if old_source and mirror_reads == 1 else SHA}}
                if path.endswith('/merge-upstream'):
                    return {'merge_type': merge_type}
                if '/releases/tags/' in path:
                    return release
                raise AssertionError(path)
            env = {'GITHUB_REPOSITORY': 'test/visualboyadvance-m', 'GITHUB_OUTPUT': str(output),
                   'GITHUB_STEP_SUMMARY': str(summary), 'GITHUB_RUN_ID': '1234',
                   'FORCE_BUILD': str(force).lower()}
            with mock.patch.dict(os.environ, env), mock.patch.object(check, 'api', side_effect=api), \
                 mock.patch.object(check, 'recipe_hash', return_value='recipe123'), \
                 mock.patch.object(check, 'keep_schedule_active'), contextlib.redirect_stdout(io.StringIO()):
                check.main()
            return dict(line.split('=', 1) for line in output.read_text().splitlines())

    def test_first_build(self):
        self.assertEqual(self.run_check()['build'], 'true')

    def test_successful_release_skipped(self):
        release = {'draft': False, 'assets': [{'name': name} for name in check.REQUIRED_ASSETS]}
        self.assertEqual(self.run_check(release)['build'], 'false')

    def test_partial_or_draft_release_retried(self):
        self.assertEqual(self.run_check({'draft': False, 'assets': []})['build'], 'true')
        release = {'draft': True, 'assets': [{'name': name} for name in check.REQUIRED_ASSETS]}
        self.assertEqual(self.run_check(release)['build'], 'true')

    def test_failed_build_retried_even_when_fork_already_synced(self):
        self.assertEqual(self.run_check()['source_sha'], SHA)
        self.assertEqual(self.run_check()['build'], 'true')

    def test_sync_and_pin_snapshot(self):
        self.assertEqual(self.run_check(old_source=True)['source_sha'], SHA)

    def test_custom_merge_not_published(self):
        with self.assertRaisesRegex(RuntimeError, 'diverged'):
            self.run_check(old_source=True, merge_type='merge')

    def test_forced_build_keeps_separate_release(self):
        self.assertTrue(self.run_check(force=True)['release_tag'].endswith('-run-1234'))


if __name__ == '__main__':
    unittest.main()
