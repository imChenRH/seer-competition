import json
import tempfile
import unittest
from pathlib import Path

from seer_demo.backends.dry_run import DryRunBackend
from seer_demo.contracts import EventWriter, validate_events, load_events
from seer_demo.engine import DemoEngine
from seer_demo.manifest import build_manifest, sha256_file


COLLISION_CERTIFICATION = {
    "collision_guard": "2.5D_OBB_SAT_SWEEP_V1",
    "collision_check_count": 100,
    "minimum_body_clearance_m": 0.15,
    "maximum_allowed_contact_error_m": 0.01,
    "forbidden_collision_count": 0,
    "collision_certified": True,
}


class ObservedIsaacBackend(DryRunBackend):
    def execute_skill(self, skill_id, attempt):
        result = super().execute_skill(skill_id, attempt)
        return result.__class__(
            success=result.success,
            duration_s=result.duration_s,
            state=result.state,
            evidence={**result.evidence, "stage_observed": True, "observed_frame": attempt},
            message=result.message,
        )

    def snapshot_evidence(self):
        return {"backend": "isaac_sim", "stage_observed": True, "observed_frame": 1}


class EvidenceManifestTests(unittest.TestCase):
    def test_manifest_revalidates_events_and_hashes_every_declared_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "isaac-normal-test"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "isaac-normal-test", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            validation = validate_events(load_events(events))
            summary = {
                **COLLISION_CERTIFICATION,
                "run_id": validation.run_id,
                "scenario": validation.scenario,
                "source": validation.source,
                "event_count": validation.event_count,
                "terminal_status": validation.terminal_status,
                "duration_s": validation.duration_s,
                "isaac_version": "6.0.1",
                "controller": "deterministic_kinematic_rule_controller",
                "resolution": "1280x720",
                "fps": 8,
                "frame_count": 409,
                "events_file": "events.jsonl",
                "video_file": "simulation.mp4",
                "scene_file": "scene.usda",
            }
            (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (run / "simulation.mp4").write_bytes(b"video")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            manifest = build_manifest(
                root,
                require_auxiliary=False,
                video_probe=lambda _: {
                    "width": 1280,
                    "height": 720,
                    "fps": 8.0,
                    "frame_count": 409,
                    "duration_s": 51.125,
                },
            )

            self.assertEqual(manifest["schema_version"], "1.0")
            self.assertEqual(len(manifest["runs"]), 1)
            recorded = manifest["runs"][0]
            self.assertEqual(recorded["terminal_status"], "COMPLETED")
            self.assertEqual(recorded["video_probe"]["frame_count"], 409)
            self.assertEqual(
                recorded["files"]["events.jsonl"]["sha256"],
                sha256_file(events),
            )

            summary["collision_certified"] = False
            (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "collision certification"):
                build_manifest(
                    root,
                    require_auxiliary=False,
                    video_probe=lambda _: {
                        "width": 1280,
                        "height": 720,
                        "fps": 8.0,
                        "frame_count": 409,
                        "duration_s": 51.125,
                    },
                )

    def test_manifest_hashes_declared_auxiliary_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "isaac-normal-test"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "isaac-normal-test", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            validation = validate_events(load_events(events))
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        **COLLISION_CERTIFICATION,
                        "run_id": validation.run_id,
                        "scenario": validation.scenario,
                        "source": validation.source,
                        "event_count": validation.event_count,
                        "terminal_status": validation.terminal_status,
                        "duration_s": validation.duration_s,
                        "resolution": "1280x720",
                        "fps": 8,
                        "frame_count": 409,
                        "events_file": "events.jsonl",
                        "video_file": "simulation.mp4",
                        "scene_file": "scene.usda",
                    }
                ),
                encoding="utf-8",
            )
            (run / "simulation.mp4").write_bytes(b"video")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")
            receipt = root / "FEISHU_LIVE_RECEIPT.json"
            receipt.write_text('{"attestation": true}\n', encoding="utf-8")
            fastwam_dir = root / "fastwam"
            fastwam_dir.mkdir()
            fastwam_log = fastwam_dir / "validation.log"
            fastwam_log.write_text("shape=[1,7]\n", encoding="utf-8")
            (fastwam_dir / "README.md").write_text("scope\n", encoding="utf-8")

            manifest = build_manifest(
                root,
                video_probe=lambda _: {
                    "width": 1280,
                    "height": 720,
                    "fps": 8.0,
                    "frame_count": 409,
                    "duration_s": 51.125,
                },
            )

            auxiliary = manifest["auxiliary_evidence"]
            self.assertEqual(
                auxiliary["FEISHU_LIVE_RECEIPT.json"]["sha256"],
                sha256_file(receipt),
            )
            self.assertEqual(
                auxiliary["fastwam/validation.log"]["sha256"],
                sha256_file(fastwam_log),
            )
            self.assertEqual(
                set(auxiliary),
                {
                    "FEISHU_LIVE_RECEIPT.json",
                    "fastwam/README.md",
                    "fastwam/validation.log",
                },
            )

    def test_manifest_hashes_and_probes_optional_presentation_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "isaac-normal-test"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "isaac-normal-test", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            validation = validate_events(load_events(events))
            summary = {
                **COLLISION_CERTIFICATION,
                "run_id": validation.run_id,
                "scenario": validation.scenario,
                "source": validation.source,
                "event_count": validation.event_count,
                "terminal_status": validation.terminal_status,
                "duration_s": validation.duration_s,
                "resolution": "1280x720",
                "fps": 8,
                "frame_count": 409,
                "presentation_resolution": "2560x1080",
                "presentation_fps": 8,
                "presentation_frame_count": 409,
                "events_file": "events.jsonl",
                "video_file": "simulation.mp4",
                "presentation_file": "presentation.mp4",
                "scene_file": "scene.usda",
            }
            (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (run / "simulation.mp4").write_bytes(b"raw")
            presentation = run / "presentation.mp4"
            presentation.write_bytes(b"presentation")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            def probe(path):
                width, height = (2560, 1080) if path.name == "presentation.mp4" else (1280, 720)
                return {"width": width, "height": height, "fps": 8.0, "frame_count": 409, "duration_s": 51.125}

            manifest = build_manifest(root, require_auxiliary=False, video_probe=probe)

            recorded = manifest["runs"][0]
            self.assertEqual(recorded["video_probe"]["width"], 1280)
            self.assertEqual(recorded["presentation_probe"]["width"], 2560)
            self.assertEqual(
                recorded["files"]["presentation.mp4"]["sha256"],
                sha256_file(presentation),
            )

    def test_manifest_rejects_presentation_that_disagrees_with_declared_resolution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "isaac-normal-test"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "isaac-normal-test", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            validation = validate_events(load_events(events))
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        **COLLISION_CERTIFICATION,
                        "run_id": validation.run_id,
                        "scenario": validation.scenario,
                        "source": validation.source,
                        "event_count": validation.event_count,
                        "terminal_status": validation.terminal_status,
                        "duration_s": validation.duration_s,
                        "events_file": "events.jsonl",
                        "video_file": "simulation.mp4",
                        "presentation_file": "presentation.mp4",
                        "presentation_resolution": "2560x1080",
                        "scene_file": "scene.usda",
                    }
                ),
                encoding="utf-8",
            )
            (run / "simulation.mp4").write_bytes(b"raw")
            (run / "presentation.mp4").write_bytes(b"bad")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "presentation resolution"):
                build_manifest(
                    root,
                    require_auxiliary=False,
                    video_probe=lambda _: {"width": 1280, "height": 720},
                )

    def test_manifest_rejects_summary_that_disagrees_with_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "run"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "run", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "run",
                        "scenario": "normal",
                        "source": "isaac_sim",
                        "event_count": 999,
                        "terminal_status": "COMPLETED",
                        "duration_s": 51.0,
                        "events_file": "events.jsonl",
                        "video_file": "simulation.mp4",
                        "scene_file": "scene.usda",
                    }
                ),
                encoding="utf-8",
            )
            (run / "simulation.mp4").write_bytes(b"video")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "summary event_count"):
                build_manifest(root, require_auxiliary=False, video_probe=lambda _: {})

    def test_manifest_rejects_semantically_truncated_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "forged-normal"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "forged-normal", "normal", "isaac_sim") as writer:
                writer.emit("task_started", 0.0, status="RUNNING")
                writer.emit("task_completed", 1.0, status="COMPLETED")
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "forged-normal",
                        "scenario": "normal",
                        "source": "isaac_sim",
                        "event_count": 2,
                        "terminal_status": "COMPLETED",
                        "duration_s": 1.0,
                        "events_file": "events.jsonl",
                        "video_file": "simulation.mp4",
                        "scene_file": "scene.usda",
                    }
                ),
                encoding="utf-8",
            )
            (run / "simulation.mp4").write_bytes(b"video")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "event trace mismatch"):
                build_manifest(root, require_auxiliary=False, video_probe=lambda _: {})

    def test_formal_manifest_requires_every_auxiliary_evidence_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run = root / "isaac-normal-test"
            run.mkdir()
            events = run / "events.jsonl"
            with EventWriter(events, "isaac-normal-test", "normal", "isaac_sim") as writer:
                DemoEngine(ObservedIsaacBackend("normal"), writer).run("normal")
            validation = validate_events(load_events(events))
            (run / "summary.json").write_text(
                json.dumps(
                    {
                        **COLLISION_CERTIFICATION,
                        "run_id": validation.run_id,
                        "scenario": validation.scenario,
                        "source": validation.source,
                        "event_count": validation.event_count,
                        "terminal_status": validation.terminal_status,
                        "duration_s": validation.duration_s,
                        "events_file": "events.jsonl",
                        "video_file": "simulation.mp4",
                        "scene_file": "scene.usda",
                    }
                ),
                encoding="utf-8",
            )
            (run / "simulation.mp4").write_bytes(b"video")
            (run / "scene.usda").write_text("#usda 1.0", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "auxiliary evidence missing"):
                build_manifest(root, video_probe=lambda _: {})


if __name__ == "__main__":
    unittest.main()
