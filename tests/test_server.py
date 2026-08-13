import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from seer_demo.backends.dry_run import DryRunBackend
from seer_demo.contracts import EventWriter, load_events, validate_events
from seer_demo.engine import DemoEngine
from seer_demo.server import create_server


ROOT = Path(__file__).resolve().parents[1]


class DemoServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.evidence_root = Path(self.temp_dir.name) / "evidence"
        run_dir = self.evidence_root / "normal-proof"
        run_dir.mkdir(parents=True)
        events_path = run_dir / "events.jsonl"
        with EventWriter(events_path, "normal-proof", "normal", "dry_run") as writer:
            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        summary = validate_events(load_events(events_path))
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "run_id": summary.run_id,
                    "scenario": summary.scenario,
                    "source": summary.source,
                    "event_count": summary.event_count,
                    "terminal_status": summary.terminal_status,
                    "duration_s": summary.duration_s,
                    "events_file": "events.jsonl",
                }
            ),
            encoding="utf-8",
        )
        self.server = create_server(
            "127.0.0.1", 0, self.evidence_root, ROOT / "demo" / "web"
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def fetch(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response.status, response.headers, response.read()

    def test_serves_console_and_allowlisted_assets(self):
        status, headers, body = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("SEER", body.decode("utf-8"))

        status, headers, _ = self.fetch("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])

    def test_lists_only_validated_evidence_runs(self):
        _, headers, body = self.fetch("/api/runs")
        payload = json.loads(body)

        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual([run["run_id"] for run in payload["runs"]], ["normal-proof"])
        self.assertEqual(payload["runs"][0]["terminal_status"], "COMPLETED")

    def test_does_not_list_structurally_valid_but_semantically_forged_run(self):
        run_dir = self.evidence_root / "forged-normal"
        run_dir.mkdir()
        events_path = run_dir / "events.jsonl"
        with EventWriter(events_path, "forged-normal", "normal", "dry_run") as writer:
            writer.emit("task_started", 0.0, status="RUNNING")
            writer.emit("task_completed", 1.0, status="COMPLETED")
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "run_id": "forged-normal",
                    "scenario": "normal",
                    "source": "dry_run",
                    "event_count": 2,
                    "terminal_status": "COMPLETED",
                    "duration_s": 1.0,
                    "events_file": "events.jsonl",
                }
            ),
            encoding="utf-8",
        )

        _, _, body = self.fetch("/api/runs")

        self.assertEqual([run["run_id"] for run in json.loads(body)["runs"]], ["normal-proof"])

    def test_does_not_list_directory_whose_name_disagrees_with_event_run_id(self):
        original = self.evidence_root / "normal-proof"
        renamed = self.evidence_root / "renamed-proof"
        original.rename(renamed)

        _, _, body = self.fetch("/api/runs")

        self.assertEqual(json.loads(body)["runs"], [])

    def test_serves_summary_and_original_ndjson_events(self):
        _, _, summary_body = self.fetch("/api/runs/normal-proof")
        _, event_headers, event_body = self.fetch("/api/runs/normal-proof/events")

        self.assertEqual(json.loads(summary_body)["run_id"], "normal-proof")
        self.assertIn("application/x-ndjson", event_headers["Content-Type"])
        self.assertEqual(len(event_body.decode("utf-8").splitlines()), json.loads(summary_body)["event_count"])

    def test_rejects_unknown_and_traversal_paths(self):
        for path in (
            "/api/runs/missing",
            "/assets/../seer_demo/contracts.py",
            "/media/normal-proof/%2E%2E%2F%2E%2E%2Fcredentials.md",
        ):
            with self.subTest(path=path):
                try:
                    self.fetch(path)
                except HTTPError as error:
                    self.assertEqual(error.code, 404)
                    error.close()
                else:
                    self.fail("unsafe path was served")


if __name__ == "__main__":
    unittest.main()
