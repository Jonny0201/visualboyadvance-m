#!/usr/bin/env python3
"""Create the source commit using GitHub's verified bot signing identity."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from check_upstream import api

BASE = '6c29df6c31f2390f9638438820d91e0e2d21143f'
UNSIGNED_ATTEMPT = '7748953bcdb56599d535b0a0c132b51396e3cdc4'
BRANCH = 'fix/coreaudio-speedup'
FILE = 'src/wx/audio/internal/coreaudio.cpp'


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    root = Path(__file__).parent / 'patches'
    patch = (root / 'coreaudio-fifo.patch').resolve()
    message = (root / 'coreaudio-fifo-message.txt').read_text()
    lines = message.splitlines()
    if len(lines[0]) > 50 or lines[0].endswith('.') or any(len(line) > 72 for line in lines[2:]):
        raise RuntimeError('Commit message does not follow upstream width requirements.')
    ref = api('GET', f'repos/{repo}/git/ref/heads/{BRANCH}')
    head = ref['object']['sha']
    if head not in (BASE, UNSIGNED_ATTEMPT):
        existing = api('GET', f'repos/{repo}/commits/{head}')
        if not existing['commit']['verification']['verified'] or existing['commit']['message'].rstrip() != message.rstrip():
            raise RuntimeError('Unexpected source branch history; refusing to rewrite it.')
        signed = head
    else:
        original = api('GET', f'repos/{repo}/contents/{FILE}?ref={BASE}')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            file = work / FILE
            file.parent.mkdir(parents=True)
            file.write_bytes(base64.b64decode(original['content']))
            subprocess.run(['git', 'init', '-q', str(work)], check=True)
            subprocess.run(['git', '-C', str(work), 'add', FILE], check=True)
            subprocess.run(['git', '-C', str(work), 'apply', '--index', str(patch)], check=True)
            content = base64.b64encode(file.read_bytes()).decode()
        if head == UNSIGNED_ATTEMPT:
            # The branch is new, has no PR, and contains only our failed signing
            # attempt. Recreate one clean, verified commit on the original base.
            api('PATCH', f'repos/{repo}/git/refs/heads/{BRANCH}', {'sha': BASE, 'force': True})
        # No custom author/committer: required for GitHub bot GPG signing.
        result = api('PUT', f'repos/{repo}/contents/{FILE}',
                     {'message': message, 'branch': BRANCH,
                      'sha': original['sha'], 'content': content})
        signed = result['commit']['sha']
        verification = api('GET', f'repos/{repo}/commits/{signed}')['commit']['verification']
        if not verification['verified'] or 'BEGIN PGP SIGNATURE' not in (verification.get('signature') or ''):
            raise RuntimeError('Source commit does not have a verified GPG signature.')
    manifest_path = '.github/vba-arm64/patches/manifest.json'
    current = api('GET', f'repos/{repo}/contents/{manifest_path}?ref=automation')
    manifest = json.loads(base64.b64decode(current['content']))
    manifest[0]['source_commit'] = signed
    body = json.dumps(manifest, indent=2) + '\n'
    update_message = (
        'build: record the signed CoreAudio fix\n\n'
        'Record the verified CoreAudio commit in the patch manifest so builds\n'
        'and release notes identify the exact contribution.\n\n'
        'Assisted-By: Codex (GPT-6) <noreply@openai.com>\n'
        'Signed-off-by: Jonny0201 <21113168+Jonny0201@users.noreply.github.com>\n'
    )
    api('PUT', f'repos/{repo}/contents/{manifest_path}',
        {'message': update_message, 'branch': 'automation', 'sha': current['sha'],
         'content': base64.b64encode(body.encode()).decode()})
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
        summary.write(f'[已驗證 GPG 簽章的音訊修正提交](https://github.com/{repo}/commit/{signed})\n')
    print(json.dumps({'signed_commit': signed, 'verified': True}))


if __name__ == '__main__':
    main()
