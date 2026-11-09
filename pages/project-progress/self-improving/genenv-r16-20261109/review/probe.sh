#!/bin/bash
set -eu
site=$(cd "$(dirname "$0")/.." && pwd)
checkout=/workspace/TacHarness-genenv
vendor=/runtime/TacHarness-genenv
runtime=/runtime/TacHarness
name=$1
out=$2
obj=$3
target=$4
shift 4
export ROBOLAB_ASSET_DIR="$runtime/inputs/datasets/vendor/robolab/assets"
export PYTHONPATH="$vendor/contrib/gujie:$checkout/src:$checkout/src/providers/RoboLab"
export ROBOLAB_POLICY_CAMERA_HEIGHT=360 ROBOLAB_POLICY_CAMERA_WIDTH=640
export TACUMI_FRANKA_USD_PATH="$vendor/contrib/gujie/configs/tacclaw_pad_friction.usda"
export OMNI_KIT_ACCEPT_EULA=Y XDG_RUNTIME_DIR=/tmp VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
export PYTHONUNBUFFERED=1
cd "$site/runs/$name"
exec "$runtime/.venv-isaacsim62/bin/python" "$checkout/scripts/agentic/probe_generated_layout.py" --task "$site/runs/$name/audit_${name//-/_}_task.py" --object "$obj" --target "$target" --out "$site/runs/$out" --seeds "$@"
