#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$repo_root/demo${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  echo "Usage: $0 check | generate [evidence-root] | serve [evidence-root] [port]" >&2
}

command_name=${1:-}
case "$command_name" in
  check)
    cd "$repo_root"
    export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
    export no_proxy="127.0.0.1,localhost${no_proxy:+,$no_proxy}"
    python3 -m unittest discover -s tests -v
    python3 -m compileall -q demo/seer_demo tests
    bash -n scripts/run_demo.sh scripts/run_isaac_demo.sh
    ;;
  generate)
    evidence_root=${2:-"$repo_root/demo/evidence/local"}
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    for scenario in normal recovery intervention; do
      run_id="dry-${scenario}-${stamp}"
      python3 -m seer_demo.cli run \
        --scenario "$scenario" \
        --output-dir "$evidence_root/$run_id" \
        --run-id "$run_id"
    done
    echo "Evidence written to: $evidence_root"
    ;;
  serve)
    evidence_root=${2:-"$repo_root/demo/evidence/local"}
    port=${3:-8765}
    if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
      echo "Port must be an integer between 1 and 65535" >&2
      exit 64
    fi
    exec python3 -m seer_demo.cli serve \
      --evidence-root "$evidence_root" \
      --host 127.0.0.1 \
      --port "$port"
    ;;
  *)
    usage
    exit 64
    ;;
esac
