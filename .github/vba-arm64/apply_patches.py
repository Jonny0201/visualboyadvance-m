#!/usr/bin/env python3
"""Apply the reviewed fork patches to a pristine upstream checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def git(source, *args, check=True):
    return subprocess.run(['git', '-C', str(source), *args], check=check,
                          capture_output=True, text=True)


def apply(source, manifest_path):
    source = Path(source).resolve()
    manifest_path = Path(manifest_path).resolve()
    entries = json.loads(manifest_path.read_text())
    patches = []
    for entry in entries:
        if not entry.get('source_commit'):
            raise RuntimeError(f"Patch {entry['id']} has no verified contribution commit.")
        path = manifest_path.parent / entry['file']
        forward = git(source, 'apply', '--check', '--index', str(path), check=False)
        if forward.returncode == 0:
            git(source, 'apply', '--index', str(path))
            status = 'applied'
        elif git(source, 'apply', '--reverse', '--check', str(path), check=False).returncode == 0:
            status = 'already present upstream'
        else:
            raise RuntimeError(f"Patch {entry['id']} no longer applies; stop for review.\n{forward.stderr}")
        patches.append({**entry, 'status': status,
                        'patch_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    changed = git(source, 'diff', '--cached', '--name-only', '-z').stdout.split('\0')
    files = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
             for name in changed if name}
    return {'patches': patches, 'modified_files_sha256': files}


if __name__ == '__main__':
    source, output = map(Path, sys.argv[1:])
    result = apply(source, Path(__file__).parent / 'patches/manifest.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
