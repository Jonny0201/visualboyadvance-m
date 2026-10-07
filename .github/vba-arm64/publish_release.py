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
    patches = json.loads((directory / 'source-patches.json').read_text())['patches']
    tag = os.environ['RELEASE_TAG']
    repo = os.environ['GITHUB_REPOSITORY']
    notes = directory / 'release-notes.txt'
    contributions = '\n'.join(
        f"- [{patch['description']}](https://github.com/{repo}/commit/{patch['source_commit']})"
        f"（{patch['status']}）" for patch in patches
    )
    notes.write_text(
        '官方 master 加上 CoreAudio 修正的 Apple Silicon 測試建置。\n\n'
        f"來源提交：`{manifest['source_commit']}`\n\n"
        f"建置設定：`{manifest['build_recipe']}`\n\n"
        '修正按住或放開 Space 後，音訊等待導致畫面停頓數秒的問題。\n\n'
        '改以 FIFO 播放並同步緩衝區使用狀態；source-patches.json 記錄實際套用的修正與提交。\n\n'
        f'{contributions}\n\n'
        '本次建置已通過完整 CTest、ARM64 架構、動態依賴、Metal 資源、簽章與啟動檢查。\n\n'
        '這是 fork 測試產物；請以新應用程式的實機測試確認 Space 切換加速的效果。\n\n'
        '包含 Metal、OpenGL、錄影與 Lua；此建置不包含 Vulkan。\n\n'
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
                        '--title', f"CoreAudio 修正 · master {manifest['source_commit'][:12]} · macOS ARM64",
                        '--notes-file', str(notes)], check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repo, '--clobber',
                    *map(str, files)], check=True)
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', repo, '--draft=false',
                    '--latest', '--notes-file', str(notes)], check=True)
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
        summary.write(f'[下載本次成功產物](https://github.com/{repo}/releases/tag/{tag})\n')


if __name__ == '__main__':
    main()
