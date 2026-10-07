#!/bin/bash
set -euo pipefail
source_dir="$1"
output_dir="$2"
[[ "$(uname -m)" == arm64 ]] || { echo 'This job requires a native ARM64 macOS runner.'; exit 1; }
mkdir -p "$output_dir"

# Metal compilation is required; obtain Apple's optional compiler component
# when the runner's selected Xcode does not already provide a working one.
probe_dir="$(mktemp -d)"
printf '#include <metal_stdlib>\nusing namespace metal;\nkernel void probe() {}\n' > "$probe_dir/probe.metal"
if ! xcrun -sdk macosx metal -c "$probe_dir/probe.metal" -o "$probe_dir/probe.air"; then
  xcodebuild -downloadComponent MetalToolchain
  xcrun -sdk macosx metal -c "$probe_dir/probe.metal" -o "$probe_dir/probe.air"
fi

brew install cmake ninja wxwidgets sdl2 zlib bzip2 xz gettext libpng libtiff ffmpeg lua openal-soft

cmake -S "$source_dir" -B "$source_dir/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_C_FLAGS_RELEASE='-O2 -g -DNDEBUG' \
  -DCMAKE_CXX_FLAGS_RELEASE='-O2 -g -DNDEBUG' \
  -DCMAKE_STRIP=/usr/bin/true \
  -DENABLE_WX=ON -DENABLE_SDL=OFF -DENABLE_SDL3=OFF -DENABLE_LIBRETRO=OFF \
  -DENABLE_VULKAN=OFF -DENABLE_FFMPEG=ON -DENABLE_LUA=ON \
  -DENABLE_ONLINEUPDATES=OFF -DENABLE_LTO=OFF -DBUNDLE_DYLIBS=ON \
  -DBUILD_TESTING=ON -DVBAM_FETCH_TEST_ROMS=OFF
cmake --build "$source_dir/build" --parallel 3
# Keep the full suite, but run scenarios sequentially on the small macOS
# runner so process/GUI timing tests are not competing with other scenarios.
ctest --test-dir "$source_dir/build" --parallel 1 --output-on-failure

app="$source_dir/build/visualboyadvance-m.app"
exe="$app/Contents/MacOS/visualboyadvance-m"
dsym="$source_dir/build/visualboyadvance-m.app.dSYM"
xcrun dsymutil "$exe" -o "$dsym"
strip -S "$exe"
for metadata in com.apple.FinderInfo com.apple.ResourceFork; do
  xattr -dr "$metadata" "$app" 2>/dev/null || true
done
sh "$source_dir/tools/macOS/codesign_app" \
  --entitlements "$source_dir/src/wx/visualboyadvance-m.entitlements" - "$app"

cp "$source_dir/LICENSE" "$output_dir/LICENSE.txt"
ditto -c -k --keepParent "$app" "$output_dir/VBA-M-macOS-arm64.zip"
ditto -c -k --keepParent "$dsym" "$output_dir/VBA-M-macOS-arm64.dSYM.zip"
python3 - "$source_dir" "$output_dir" <<'PY'
import datetime, json, os, pathlib, subprocess, sys
source, output = map(pathlib.Path, sys.argv[1:])
def command(*args):
    return subprocess.check_output(args, text=True).strip()
manifest = {
    'source_repository': 'visualboyadvance-m/visualboyadvance-m',
    'source_branch': 'master',
    'source_commit': os.environ['UPSTREAM_SHA'],
    'source_patches': [],
    'pipeline_commit': os.environ['GITHUB_SHA'],
    'build_recipe': os.environ['BUILD_RECIPE'],
    'build_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'architecture': command('uname', '-m'),
    'macos': command('sw_vers', '-productVersion'),
    'xcode': command('xcodebuild', '-version'),
    'minimum_macos': '15.0',
    'signature': 'ad-hoc, upstream sandbox entitlements; not notarized',
    'workflow_url': os.environ['GITHUB_SERVER_URL'] + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'],
    'capabilities': {'metal': True, 'ffmpeg_recording': True, 'lua': True, 'vulkan': False},
}
actual = command('git', '-C', str(source), 'rev-parse', 'HEAD')
if actual != manifest['source_commit']:
    raise SystemExit('Source revision does not match the checked upstream snapshot.')
(output / 'build-info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
PY
(cd "$output_dir" && shasum -a 256 ./*.zip build-info.json LICENSE.txt > SHA256SUMS.txt)
