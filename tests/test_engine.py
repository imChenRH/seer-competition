import tempfile
import unittest
from pathlib import Path

from seer_demo.backends.dry_run import DryRunBackend
from seer_demo.contracts import EventWriter, load_events, validate_events
from seer_demo.engine import ActionResult
from seer_demo.engine import DemoEngine
from seer_demo.scenarios import SKILL_SEQUENCE


class DemoEngineTests(unittest.TestCase):
    def run_scenario(self, scenario):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "events.jsonl"
        backend = DryRunBackend(scenario)
        with EventWriter(path, f"run-{scenario}-001", scenario, "dry_run") as writer:
            result = DemoEngine(backend, writer).run(scenario)
        events = load_events(path)
        return result, events

    def test_normal_completes_exact_nine_skill_sequence_without_fallback(self):
        result, events = self.run_scenario("normal")

        completed = [event.skill_id for event in events if event.event_type == "skill_completed"]

        self.assertEqual(completed, list(SKILL_SEQUENCE))
        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(any(event.fallback_id for event in events))
        self.assertEqual(validate_events(events).terminal_status, "COMPLETED")
        self.assertTrue(events[-1].state["payload_placed"])

    def test_recovery_uses_fb_f01_then_completes_all_skills(self):
        result, events = self.run_scenario("recovery")

        fallbacks = [event.fallback_id for event in events if event.event_type == "fallback_started"]
        completed = [event.skill_id for event in events if event.event_type == "skill_completed"]
        per_attempts = [
            event.evidence["attempt"]
            for event in events
            if event.skill_id == "FORK-PER-01" and event.event_type in {"skill_failed", "skill_completed"}
        ]

        self.assertEqual(fallbacks, ["FB-F01"])
        self.assertEqual(per_attempts, [1, 2])
        self.assertEqual(completed, list(SKILL_SEQUENCE))
        self.assertEqual(result.status, "COMPLETED")
        self.assertTrue(any(event.state.get("lateral_correction_m") for event in events))

    def test_intervention_exhausts_fb_f02_and_stops_for_human(self):
        result, events = self.run_scenario("intervention")

        failed_attempts = [
            event.evidence["attempt"]
            for event in events
            if event.event_type == "skill_failed" and event.skill_id == "FORK-PER-01"
        ]
        fallbacks = [event.fallback_id for event in events if event.event_type == "fallback_started"]
        completed = [event.skill_id for event in events if event.event_type == "skill_completed"]

        self.assertEqual(failed_attempts, [1, 2, 3])
        self.assertEqual(fallbacks, ["FB-F02", "FB-F07"])
        self.assertEqual(completed, list(SKILL_SEQUENCE[:2]))
        self.assertEqual(result.status, "HUMAN_REQUIRED")
        self.assertEqual(events[-2].event_type, "safety_stop")
        self.assertEqual(events[-1].event_type, "human_intervention_requested")
        self.assertTrue(events[-1].state["stopped"])
        self.assertTrue(events[-1].state["safe_retreat_complete"])
        self.assertEqual(validate_events(events).terminal_status, "HUMAN_REQUIRED")

    def test_unknown_scenario_fails_before_writing_success(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "events.jsonl"

        with EventWriter(path, "run-bad", "unknown", "dry_run") as writer:
            with self.assertRaisesRegex(ValueError, "unknown scenario"):
                DemoEngine(DryRunBackend("normal"), writer).run("unknown")

    def test_failed_intervention_view_fallback_cannot_reach_human_terminal(self):
        class FailedViewFallbackBackend(DryRunBackend):
            def execute_fallback(self, fallback_id, attempt):
                result = super().execute_fallback(fallback_id, attempt)
                if fallback_id == "FB-F02":
                    return ActionResult(False, result.duration_s, result.state, result.evidence, "failed")
                return result

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            with EventWriter(path, "run-intervention-failed-fallback", "intervention", "dry_run") as writer:
                with self.assertRaisesRegex(RuntimeError, "FB-F02"):
                    DemoEngine(FailedViewFallbackBackend("intervention"), writer).run("intervention")
            events = load_events(path)

        self.assertFalse(any(event.event_type == "human_intervention_requested" for event in events))

    def test_failed_safety_stop_cannot_claim_human_terminal(self):
        class FailedStopBackend(DryRunBackend):
            def safety_stop(self):
                state = self.snapshot()
                state["stopped"] = False
                return ActionResult(False, 1.0, state, {"velocity_verified": 0.4}, "still moving")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            with EventWriter(path, "run-intervention-failed-stop", "intervention", "dry_run") as writer:
                with self.assertRaisesRegex(RuntimeError, "safety stop"):
                    DemoEngine(FailedStopBackend("intervention"), writer).run("intervention")
            events = load_events(path)

        self.assertFalse(any(event.event_type == "human_intervention_requested" for event in events))


if __name__ == "__main__":
    unittest.main()
