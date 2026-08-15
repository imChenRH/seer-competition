"""Deployable Feishu-to-Isaac bridge command."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
import time

try:
    import fcntl
except ImportError:  # Windows: use msvcrt byte-range locking below
    fcntl = None
if os.name == "nt":
    import msvcrt
else:
    msvcrt = None

from .bridge import SubprocessRunner, TaskBridge
from .feishu import FeishuApiError, FeishuClient, FeishuSettings, load_env_file


class BridgeInstanceLock:
    """Hold one OS-level advisory lock for a bridge evidence workspace.

    POSIX uses ``fcntl.flock``. Windows uses ``msvcrt.locking`` on the first
    byte of the lock file, which provides the same fail-closed single-instance
    guarantee for the bridge process.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            if msvcrt is not None:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write('\n')
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            raise RuntimeError(
                f"another bridge instance is already active for {self.path.parent}"
            ) from exc
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._handle is not None:
            try:
                if msvcrt is not None:
                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            finally:
                self._handle.close()
                self._handle = None


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one idempotent Feishu-to-Isaac bridge")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
    )
    parser.add_argument("--isaac-python", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--fps", type=_positive_int, default=2)
    parser.add_argument("--resolution", default="640x360")
    parser.add_argument("--bridge-id", default="")
    parser.add_argument("--poll-interval", type=_positive_float, default=5.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--skip-field-bootstrap",
        action="store_true",
        help="do not create/verify the numeric last-event field",
    )
    return parser.parse_args(argv)


def build_runner_command(args: argparse.Namespace) -> tuple[str, ...]:
    return (
        str(args.isaac_python),
        "-m",
        "seer_demo.isaac.runner",
        "--fps",
        str(args.fps),
        "--resolution",
        args.resolution,
    )


def resolve_bridge_id(args: argparse.Namespace) -> str:
    bridge_id = args.bridge_id or os.environ.get("BRIDGE_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", bridge_id):
        raise ValueError(
            "a stable bridge id is required via --bridge-id or BRIDGE_ID "
            "(letters, numbers, dot, underscore and hyphen only)"
        )
    return bridge_id


def run(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    bridge_id = resolve_bridge_id(args)
    with BridgeInstanceLock(args.evidence_root / ".bridge.lock"):
        settings = FeishuSettings.from_environment()
        client = FeishuClient(settings)
        if not args.skip_field_bootstrap:
            client.ensure_number_field(settings.tasks_table, "最后事件序号")
        runner = SubprocessRunner(build_runner_command(args), args.evidence_root)
        bridge = TaskBridge(client, runner, bridge_id)
        while True:
            outcomes = bridge.process_once()
            if outcomes:
                print(
                    json.dumps([asdict(item) for item in outcomes], ensure_ascii=False),
                    flush=True,
                )
            if args.once:
                return 0
            time.sleep(args.poll_interval)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except KeyboardInterrupt:
        return 130
    except (FeishuApiError, OSError, RuntimeError, ValueError) as exc:
        print(f"bridge error: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
