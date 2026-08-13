import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DemoCliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "demo")
        return subprocess.run(
            [sys.executable, "-m", "seer_demo.cli", *arguments],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

    def test_run_writes_valid_events_and_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_cli(
                "run",
                "--scenario",
                "recovery",
                "--output-dir",
                temp_dir,
                "--run-id",
                "cli-recovery-001",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((Path(temp_dir) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["run_id"], "cli-recovery-001")
            self.assertEqual(summary["scenario"], "recovery")
            self.assertEqual(summary["source"], "dry_run")
            self.assertEqual(summary["terminal_status"], "COMPLETED")
            self.assertTrue((Path(temp_dir) / "events.jsonl").is_file())

    def test_validate_reports_malformed_log_as_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.jsonl"
            path.write_text("not-json\n", encoding="utf-8")

            result = self.run_cli("validate", str(path))

            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid JSONL", result.stderr)

    def test_documented_isaac_script_interface_accepts_scenario_output_and_run_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["ISAAC_SIM_ROOT"] = str(Path(temp_dir) / "missing-isaac")
            result = subprocess.run(
                [
                    "bash",
                    "scripts/run_isaac_demo.sh",
                    "normal",
                    str(Path(temp_dir) / "evidence"),
                    "isaac-normal-doc-test",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )

            self.assertEqual(result.returncode, 69, result.stderr)
            self.assertIn("Isaac python launcher not found", result.stderr)
            self.assertNotIn("Usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
