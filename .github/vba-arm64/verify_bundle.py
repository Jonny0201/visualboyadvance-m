#!/usr/bin/env python3
"""Reject non-ARM64 or non-portable app bundles before publishing."""
from pathlib import Path
import plistlib
import subprocess
import sys


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def main():
    app = Path(sys.argv[1]).resolve()
    plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if not plist.get('CFBundleIdentifier') or not plist.get('CFBundleName'):
        raise SystemExit('Missing application identity.')
    executable = app / 'Contents/MacOS' / plist['CFBundleExecutable']
    if command('lipo', '-archs', str(executable)) != 'arm64':
        raise SystemExit('The main executable is not a native arm64 binary.')
    if not (app / 'Contents/Resources/default.metallib').is_file():
        raise SystemExit('Missing compiled Metal shaders.')
    checked = 0
    forbidden = []
    for file in app.rglob('*'):
        if not file.is_file() or file.is_symlink():
            continue
        if not command('file', '-b', str(file)).startswith('Mach-O'):
            continue
        arches = command('lipo', '-archs', str(file)).split()
        if 'arm64' not in arches:
            forbidden.append(f'Non-ARM64 dependency: {file}')
        for line in command('otool', '-L', str(file)).splitlines()[1:]:
            dependency = line.strip().split(' (compatibility', 1)[0]
            if dependency.startswith('/') and not dependency.startswith(('/System/Library/', '/usr/lib/')):
                forbidden.append(f'Unbundled absolute dependency: {file} -> {dependency}')
        checked += 1
    if forbidden:
        raise SystemExit('\n'.join(forbidden))
    command('codesign', '--verify', '--deep', '--strict', str(app))
    # CLI startup only: no game or personal save file is involved.
    smoke = subprocess.run([str(executable), '--help'], capture_output=True, text=True, timeout=45)
    if smoke.returncode != 0:
        raise SystemExit(f'CLI startup failed: {smoke.returncode}\n{smoke.stdout}\n{smoke.stderr}')
    print(f'Validated native arm64 bundle with {checked} Mach-O files, compiled Metal shaders, signature, and CLI startup.')


if __name__ == '__main__':
    main()
