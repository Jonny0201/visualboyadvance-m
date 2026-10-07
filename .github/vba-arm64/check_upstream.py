#!/usr/bin/env python3
"""Mirror upstream and build only versions without a complete successful release."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

UPSTREAM = 'visualboyadvance-m/visualboyadvance-m'
REQUIRED_ASSETS = {'VBA-M-macOS-arm64.zip', 'build-info.json', 'SHA256SUMS.txt'}


def api(method, path, data=None, missing_ok=False):
    request = urllib.request.Request(
        'https://api.github.com/' + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28',
                 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        message = json.loads(error.read()).get('message', str(error))
        raise RuntimeError(f'GitHub API {method} {path}: {error.code} {message}') from None


def recipe_hash(root):
    files = sorted((root / '.github/vba-arm64').glob('*.py'))
    files += sorted((root / '.github/vba-arm64').glob('*.sh'))
    files += [root / '.github/workflows/upstream-arm64.yml']
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()[:12]


def keep_schedule_active(repo):
    # A small status commit only when 40 days have passed. It does not change
    # the source mirror or the build recipe, and prevents idle schedules expiring.
    path = f'repos/{repo}/contents/AUTOMATION_ACTIVITY.json?ref=automation'
    current = api('GET', path, missing_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    last = None
    if current:
        old = json.loads(base64.b64decode(current['content']))
        last = dt.datetime.fromisoformat(old['last_keepalive_utc'])
    if last and (now - last).days < 40:
        return
    payload = {'message': 'ci: keep scheduled upstream checks active', 'branch': 'automation',
               'content': base64.b64encode((json.dumps({'last_keepalive_utc': now.isoformat()},
                                                     indent=2) + '\n').encode()).decode()}
    if current:
        payload['sha'] = current['sha']
    api('PUT', f'repos/{repo}/contents/AUTOMATION_ACTIVITY.json', payload)


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    metadata = api('GET', f'repos/{repo}')
    if not metadata.get('fork') or metadata.get('parent', {}).get('full_name') != UPSTREAM:
        raise RuntimeError('Repository is not a fork of the expected upstream.')
    official = api('GET', f'repos/{UPSTREAM}/git/ref/heads/master')['object']['sha']
    ours = api('GET', f'repos/{repo}/git/ref/heads/master')['object']['sha']
    if ours != official:
        synced = api('POST', f'repos/{repo}/merge-upstream', {'branch': 'master'})
        if synced.get('merge_type') not in ('fast-forward', None):
            raise RuntimeError('The mirror has diverged; refusing to publish a merged custom source.')
        ours = api('GET', f'repos/{repo}/git/ref/heads/master')['object']['sha']
    if not re.fullmatch('[0-9a-f]{40}', ours):
        raise RuntimeError('Unexpected upstream commit format.')
    recipe = recipe_hash(Path.cwd())
    tag = f'upstream-{ours[:12]}-recipe-{recipe}'
    force = os.environ.get('FORCE_BUILD', '').lower() == 'true'
    if force:
        tag += '-run-' + os.environ['GITHUB_RUN_ID']
    release = api('GET', f'repos/{repo}/releases/tags/{tag}', missing_ok=True)
    complete = bool(release and not release['draft'] and
                    REQUIRED_ASSETS <= {a['name'] for a in release['assets']})
    build = not complete
    keep_schedule_active(repo)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write(f'build={str(build).lower()}\nsource_sha={ours}\nrelease_tag={tag}\nrecipe={recipe}\n')
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as output:
        output.write(f'官方提交：`{ours}`\n\n建置設定：`{recipe}`\n\n'
                     f'{"開始建置" if build else "已有完整成功產物，略過建置"}。\n')
    print(json.dumps({'source_sha': ours, 'recipe': recipe, 'release_tag': tag, 'build': build}))


if __name__ == '__main__':
    main()
