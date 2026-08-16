#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 <python> <model-dir> <output-dir> <run-id>" >&2
  exit 64
fi

python_bin=$1
model_dir=$2
output_dir=$3
run_id=$4
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

[[ $(uname -s) == Linux ]] || { echo "Fast-WAM LIBERO rollout requires Linux" >&2; exit 69; }
[[ -x "$python_bin" ]] || { echo "Python is not executable: $python_bin" >&2; exit 69; }
[[ -f "$model_dir/config.json" && -f "$model_dir/model.safetensors" ]] || {
  echo "Fast-WAM checkpoint is incomplete: $model_dir" >&2
  exit 69
}
[[ ! -e "$output_dir" ]] || { echo "Output directory already exists: $output_dir" >&2; exit 73; }

"$python_bin" -c 'import mujoco; assert mujoco.__version__ == "3.3.2"'
"$python_bin" -c 'import torch; assert torch.cuda.is_available()'
"$python_bin" -c 'import libero, robosuite'

available_kb=$(df -Pk "$(dirname "$output_dir")" | awk 'NR==2 {print $4}')
minimum_kb=$((10 * 1024 * 1024))
if (( available_kb < minimum_kb )); then
  echo "At least 10 GiB free disk is required for five recorded attempts" >&2
  exit 69
fi

export MUJOCO_GL=egl
export PYTHONPATH="$repo_root/demo${PYTHONPATH:+:$PYTHONPATH}"
exec "$python_bin" -m seer_demo.fastwam.rollout \
  --model-dir "$model_dir" \
  --output-dir "$output_dir" \
  --run-id "$run_id" \
  --attempts 5 \
  --fps 20 \
  --width 1280 \
  --height 720 \
  --max-steps 300
