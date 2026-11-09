#!/usr/bin/env bash
set -eu
site=$(cd "$(dirname "$0")/.." && pwd)
src=/workspace/TacHarness-genenv
vendor=/runtime/TacHarness-genenv
runtime=/runtime/TacHarness
case_dir=$1
out="$site/runs/$2"
mkdir -p "$out"
cd "$out"
export ROBOLAB_ASSET_DIR="$runtime/inputs/datasets/vendor/robolab/assets"
export PYTHONPATH="$vendor/contrib/gujie:$src/src:$src/src/providers/RoboLab:$src/src/providers/LIBERO/source/tac_manip"
export TACHARNESS_LEROBOT_ENV=/runtime/.conda/tacharness-lerobot312
export OMNI_KIT_ACCEPT_EULA=YES
exec "$runtime/.venv-isaacsim62/bin/python" -m gpt_rollout.robolab_run --task "$site/runs/$case_dir/audit_${case_dir}_task.py" --policy scripted --scripted-object "$3" --scripted-target "$4" --seed-start 71 --num-seeds "${5:-1}" --time-limit-scale 1 --output-root "$out"
