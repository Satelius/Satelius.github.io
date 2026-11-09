#!/bin/bash
set -eu
d=${GENENV_UNI_ROOT:-/workspace/TacHarness-genenv/outputs/genenv-audit-20261109/uni60}
src=/runtime/UniVTAC/third_party/TacEx/source
py=/runtime/gujie/TacHarness/.venv-isaacsim60/bin/python
cd "$d/work"
export PYTHONPATH="$d/work:$d/overlay:$src/tacex:$src/tacex_assets:$src/tacex_uipc:$d/curobo/src"
export PYTHONUNBUFFERED=1 OMNI_KIT_ACCEPT_EULA=YES XDG_RUNTIME_DIR=/tmp VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
export LD_LIBRARY_PATH="/runtime/gujie/.local/lib:${LD_LIBRARY_PATH:-}"
legacy=/runtime/gujie/TacHarness/.venv-isaacsim60/lib/python3.12/site-packages/isaacsim/extsDeprecated
foundation=$(find "${legacy%/extsDeprecated}"/extscache/omni.gpu_foundation-* -name libglib-2.0.so.0 | head -1)
export LD_PRELOAD="$foundation"
export GENENV_UNI_DIAG="/workspace/summary-web/genenv-r16-20261109/runs/${2:-uni-default}-startup"
extra=()
if [ -n "${3:-}" ]; then extra+=("task_overrides.can_sizes=[$3]"); fi
if [ -n "${GENENV_BOTTLE_CONDITION:-}" ]; then extra+=("task_overrides.condition=$GENENV_BOTTLE_CONDITION"); fi
exec "$py" scripts/collect_data.py "${1:-put_bottle_in_shelf}" demo --start_seed 1 --max_seed 1 --headless --kit_args="--ext-folder $legacy --enable isaacsim.core.api --enable isaacsim.core.prims --enable isaacsim.core.cloner" --config-overrides collect_settings.episode_num=1 collect_settings.save_root_dir="$d/${2:-native}" "${extra[@]}"
