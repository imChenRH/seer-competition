import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seer_demo.bridge_cli import (
    BridgeInstanceLock,
    build_runner_command,
    parse_args,
    resolve_bridge_id,
)


class BridgeCliTests(unittest.TestCase):
    def test_exclusive_lock_prevents_second_bridge_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "bridge.lock"
            with BridgeInstanceLock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with BridgeInstanceLock(lock_path):
                        pass
            with BridgeInstanceLock(lock_path):
                pass

    def test_builds_shell_free_isaac_command_with_explicit_quality(self):
        args = parse_args(
            [
                "--isaac-python",
                "/opt/isaac/python.sh",
                "--evidence-root",
                "/data/evidence",
                "--fps",
                "2",
                "--resolution",
                "640x360",
                "--once",
            ]
        )

        self.assertEqual(
            build_runner_command(args),
            (
                str(Path("/opt/isaac/python.sh")),
                "-m",
                "seer_demo.isaac.runner",
                "--fps",
                "2",
                "--resolution",
                "640x360",
            ),
        )
        self.assertEqual(args.evidence_root, Path("/data/evidence"))
        self.assertTrue(args.once)

    def test_rejects_invalid_poll_interval_before_contacting_feishu(self):
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--isaac-python",
                    "/opt/isaac/python.sh",
                    "--evidence-root",
                    "/data/evidence",
                    "--poll-interval",
                    "0",
                ]
            )

    def test_bridge_id_must_be_stable_and_explicit(self):
        args = parse_args(
            [
                "--isaac-python",
                "/opt/isaac/python.sh",
                "--evidence-root",
                "/data/evidence",
            ]
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "stable bridge id"):
                resolve_bridge_id(args)

        args.bridge_id = "autodl-isaac-primary"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_bridge_id(args), "autodl-isaac-primary")


if __name__ == "__main__":
    unittest.main()
