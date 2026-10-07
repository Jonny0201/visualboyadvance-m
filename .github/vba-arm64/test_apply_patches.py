import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('apply_patches', Path(__file__).with_name('apply_patches.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PATCH = 'diff --git a/audio.txt b/audio.txt\n--- a/audio.txt\n+++ b/audio.txt\n@@ -1 +1 @@\n-timestamps\n+fifo\n'


class ApplyTests(unittest.TestCase):
    def fixture(self, root, content='timestamps\n', signed=True):
        source = root / 'source'
        source.mkdir()
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        (source / 'audio.txt').write_text(content)
        subprocess.run(['git', '-C', str(source), 'add', 'audio.txt'], check=True)
        subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c',
                        'user.email=test@example.invalid', 'commit', '-qm', 'baseline'], check=True)
        directory = root / 'patches'
        directory.mkdir()
        (directory / 'fix.patch').write_text(PATCH)
        manifest = directory / 'manifest.json'
        manifest.write_text(json.dumps([{'id': 'test', 'file': 'fix.patch',
                                        'source_commit': 'a' * 40 if signed else None}]))
        return source, manifest

    def test_applies_and_records_built_file(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest = self.fixture(Path(name))
            result = module.apply(source, manifest)
            self.assertEqual((source / 'audio.txt').read_text(), 'fifo\n')
            self.assertEqual(result['patches'][0]['status'], 'applied')
            self.assertIn('audio.txt', result['modified_files_sha256'])

    def test_already_fixed_upstream(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest = self.fixture(Path(name), 'fifo\n')
            result = module.apply(source, manifest)
            self.assertEqual(result['patches'][0]['status'], 'already present upstream')
            self.assertEqual(result['modified_files_sha256'], {})

    def test_conflict_stops_before_build(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest = self.fixture(Path(name), 'changed upstream\n')
            with self.assertRaisesRegex(RuntimeError, 'no longer applies'):
                module.apply(source, manifest)
            self.assertEqual((source / 'audio.txt').read_text(), 'changed upstream\n')

    def test_missing_verified_commit_stops(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest = self.fixture(Path(name), signed=False)
            with self.assertRaisesRegex(RuntimeError, 'verified contribution'):
                module.apply(source, manifest)


if __name__ == '__main__':
    unittest.main()
