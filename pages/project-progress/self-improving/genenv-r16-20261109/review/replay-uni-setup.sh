#!/usr/bin/env bash
# Create a new source overlay and reuse the verified native binaries.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?supply a new directory}
if [[ -e "$out" ]]; then echo "destination exists: $out" >&2; exit 2; fi
up=/runtime/UniVTAC
sim=/runtime/gujie/TacHarness/.venv-isaacsim60/bin/python
audit=/workspace/TacHarness-genenv/outputs/genenv-audit-20261109/uni60
mkdir -p "$out/work" "$out/overlay"
cp -a "$up/envs" "$up/scripts" "$up/task_config" "$out/work/"
ln -s "$up/assets" "$out/work/assets"
cp -a "$audit/overlay/." "$out/overlay/"
cp -a "$up/third_party/TacEx/source/tacex_uipc/tacex_uipc/." "$out/overlay/tacex_uipc/"
cp -a "$up/third_party/TacEx/source/tacex/tacex/." "$out/overlay/tacex/"
cp -a "$audit/curobo" "$out/curobo"
(cd "$out" && git apply --check "$here/uni60.patch" && git apply "$here/uni60.patch")
PYTHONPATH="$out/overlay" "$sim" -c 'import uipc; print("pyuipc",uipc.__version__)'
echo "$out"
