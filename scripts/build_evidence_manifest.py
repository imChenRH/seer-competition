#!/usr/bin/env python3
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "demo"))

from seer_demo.manifest import build_manifest  # noqa: E402


def main() -> int:
    evidence_root = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "demo" / "evidence"
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else evidence_root / "MANIFEST.json"
    manifest = build_manifest(evidence_root)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["environment"] = {
        "simulator": "Isaac Sim 6.0.1",
        "recording_host": "AutoDL Linux / NVIDIA RTX 4090",
        "controller": "deterministic kinematic rule controller",
        "payload_model": "explicit attach/release coupling",
    }
    manifest["claim_boundary"] = (
        "Demonstration-grade kinematic digital twin; not hardware, ROS 2, real perception, "
        "Fast-WAM forklift control, calibrated dynamics, or production safety evidence."
    )
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
