#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <normal|recovery|intervention> <output-dir> [run-id]" >&2
  exit 64
fi

scenario=$1
output_dir=$2
run_id=${3:-"isaac-${scenario}-$(date -u +%Y%m%dT%H%M%SZ)"}
isaac_root=${ISAAC_SIM_ROOT:-/root/autodl-tmp/isaacsim601}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

case "$scenario" in
  normal|recovery|intervention) ;;
  *) echo "Unknown scenario: $scenario" >&2; exit 64 ;;
esac

if [[ ! -x "$isaac_root/python.sh" ]]; then
  echo "Isaac python launcher not found: $isaac_root/python.sh" >&2
  exit 69
fi

export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONPATH="$repo_root/demo${PYTHONPATH:+:$PYTHONPATH}"
runner_args=(
  -m seer_demo.isaac.runner
  --scenario "$scenario"
  --output-dir "$output_dir"
  --run-id "$run_id"
)
if [[ -n "${ISAAC_WAREHOUSE_ASSET_ROOT:-}" ]]; then
  runner_args+=(--warehouse-asset-root "$ISAAC_WAREHOUSE_ASSET_ROOT")
fi
exec "$isaac_root/python.sh" "${runner_args[@]}"
