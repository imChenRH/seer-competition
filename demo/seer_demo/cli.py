"""Command line entry point for local evidence runs and validation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

from .backends.dry_run import DryRunBackend
from .contracts import EventWriter, load_events, validate_scenario_events
from .engine import DemoEngine
from .scenarios import SCENARIOS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SEER evidence-driven forklift Demo")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a deterministic Mac dry-run")
    run.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--run-id")
    validate = commands.add_parser("validate", help="validate a JSONL evidence log")
    validate.add_argument("path", type=Path)
    serve = commands.add_parser("serve", help="serve the validated evidence console")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--evidence-root", type=Path, required=True)
    serve.add_argument("--web-root", type=Path, default=Path(__file__).resolve().parents[1] / "web")
    return parser


def _default_run_id(scenario: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"dry-{scenario}-{stamp}-{uuid.uuid4().hex[:6]}"


def run_command(args: argparse.Namespace) -> int:
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "events.jsonl"
    run_id = args.run_id or _default_run_id(args.scenario)
    with EventWriter(events_path, run_id, args.scenario, "dry_run") as writer:
        DemoEngine(DryRunBackend(args.scenario), writer).run(args.scenario)
    validation = validate_scenario_events(load_events(events_path), expected_scenario=args.scenario)
    summary = asdict(validation)
    summary["events_file"] = "events.jsonl"
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def validate_command(args: argparse.Namespace) -> int:
    validation = validate_scenario_events(load_events(args.path))
    print(json.dumps(asdict(validation), ensure_ascii=False))
    return 0


def serve_command(args: argparse.Namespace) -> int:
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    from .server import create_server

    server = create_server(args.host, args.port, args.evidence_root, args.web_root)
    print(f"SEER evidence console: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_command(args)
        if args.command == "validate":
            return validate_command(args)
        return serve_command(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
