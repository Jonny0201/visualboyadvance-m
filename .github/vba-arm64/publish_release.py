#!/usr/bin/env python3
"""Publish directly from the build runner; no Actions Artifact upload is used."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    directory = Path(sys.argv[1])
    files = sorted(p for p in directory.iterdir() if p.is_file())
    if any(p.stat().st_size >= 2 * 1024**3 for p in files):
        raise SystemExit('A release asset is at or above the GitHub 2 GiB limit.')
    manifest = json.loads((directory / 'build-info.json').read_text())
    tag = os.environ['RELEASE_TAG']
    repo = os.environ['GITHUB_REPOSITORY']
    notes = directory / 'release-notes.txt'
    notes.write_text(
        '官方 master 的 Apple Silicon 自動建置。\n\n'
        f"來源提交：`{manifest['source_commit']}`\n\n"
        f"建置設定：`{manifest['build_recipe']}`\n\n"
        '沒有套用本機的額外音訊修正。包含 Metal、OpenGL、錄影與 Lua；此建置不包含 Vulkan。\n\n'
        '下載 VBA-M-macOS-arm64.zip，解壓縮後取得應用程式。最低 macOS 15。\n\n'
        '採用本機式簽章，未經 Apple 公證；首次開啟可能需要使用者在 macOS 確認。\n\n'
        '除錯符號供日後排查使用；SHA256SUMS.txt 可驗證下載檔。\n\n'
        f"[建置與測試紀錄]({manifest['workflow_url']})\n",
    )
    exists = subprocess.run(['gh', 'release', 'view', tag, '--repo', repo],
                            capture_output=True, text=True).returncode == 0
    if not exists:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', repo,
                        '--target', manifest['source_commit'], '--draft',
                        '--title', f"官方 master {manifest['source_commit'][:12]} · macOS ARM64",
                        '--notes-file', str(notes)], check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repo, '--clobber',
                    *map(str, files)], check=True)
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', repo, '--draft=false',
                    '--latest', '--notes-file', str(notes)], check=True)
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
        summary.write(f'[下載本次成功產物](https://github.com/{repo}/releases/tag/{tag})\n')


if __name__ == '__main__':
    main()
