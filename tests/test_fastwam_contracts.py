import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from seer_demo.contracts import EventWriter, load_events
from seer_demo.fastwam.contracts import (
    ActionRecord,
    FASTWAM_SCENARIO,
    FASTWAM_SKILLS,
    POLICY_CONFIG_SHA256,
    POLICY_REPOSITORY,
    POLICY_REVISION,
    POLICY_WEIGHTS_SHA256,
    load_action_records,
    validate_action_records,
    validate_fastwam_events,
    validate_fastwam_package,
)


class FastWamContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_events(self, run_id="wam-1", *, success=True):
        path = self.root / f"{run_id}.jsonl"
        with EventWriter(path, run_id, FASTWAM_SCENARIO, "fastwam_policy") as writer:
            writer.emit("task_started", 0.0, status="RUNNING")
            for offset, skill_id in enumerate(FASTWAM_SKILLS, 1):
                writer.emit(
                    "skill_started",
                    offset * 0.1,
                    status="RUNNING",
                    skill_id=skill_id,
                )
                if success or skill_id != "ARM-VER-01":
                    writer.emit(
                        "skill_completed",
                        offset * 0.1 + 0.05,
                        status="RUNNING",
                        skill_id=skill_id,
                        state={"official_success": skill_id == "ARM-VER-01"},
                        evidence={"observed_frame": offset},
                    )
            if success:
                writer.emit(
                    "task_completed",
                    1.0,
                    status="COMPLETED",
                    state={"official_success": True},
                    evidence={"observed_frame": 9},
                )
            else:
                writer.emit(
                    "task_failed",
                    1.0,
                    status="FAILED",
                    state={"official_success": False},
                    evidence={"observed_frame": 9},
                )
        return load_events(path)

    @staticmethod
    def make_actions(run_id="wam-1"):
        return [
            ActionRecord("1.0", run_id, 0, 0, 0.0, (0.0,) * 7, True, 0.21),
            ActionRecord("1.0", run_id, 1, 1, 0.05, (0.1,) * 7, False, 0.001),
        ]

    @staticmethod
    def make_summary(run_id="wam-1", *, selected_attempt=2):
        attempts = [
            {
                "attempt_index": index,
                "seed": 202608160 + index,
                "init_state_id": index,
                "success": index == selected_attempt,
                "executed_steps": 80 + index,
                "policy_calls": 8 + index,
                "terminal_reason": "success" if index == selected_attempt else "timeout",
            }
            for index in range(5)
        ]
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "scenario": FASTWAM_SCENARIO,
            "source": "fastwam_policy",
            "event_count": 18,
            "terminal_status": "COMPLETED",
            "duration_s": 1.0,
            "frame_count": 10,
            "action_count": 2,
            "policy_call_count": 1,
            "policy_repository": POLICY_REPOSITORY,
            "policy_revision": POLICY_REVISION,
            "policy_config_sha256": POLICY_CONFIG_SHA256,
            "policy_weights_sha256": POLICY_WEIGHTS_SHA256,
            "official_success": True,
            "attempt_count": 5,
            "attempts": attempts,
            "selected_attempt": selected_attempt,
        }

    def test_formal_scenario_is_canonical_bowl_on_plate(self):
        self.assertEqual(FASTWAM_SCENARIO, "fastwam_bowl_plate")

    def test_writer_accepts_fastwam_policy_source(self):
        events = self.make_events()
        self.assertEqual(events[0].source, "fastwam_policy")

    def test_actions_require_contiguous_finite_7d_values(self):
        valid = self.make_actions()
        result = validate_action_records(valid, "wam-1", frame_count=2)
        self.assertEqual(result.action_count, 2)
        self.assertEqual(result.policy_call_count, 1)
        for broken in (
            [replace(valid[0], sequence=2)],
            [replace(valid[0], action=(0.0,) * 6)],
            [replace(valid[0], action=(math.nan,) + (0.0,) * 6)],
            [replace(valid[0], action=(1.01,) + (0.0,) * 6)],
            [replace(valid[0], observed_frame=2)],
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    validate_action_records(broken, "wam-1", frame_count=2)

    def test_action_jsonl_loader_rejects_unknown_fields(self):
        path = self.root / "actions.jsonl"
        value = self.make_actions()[0].to_dict()
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.assertEqual(load_action_records(path), [self.make_actions()[0]])
        value["invented"] = True
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_action_records(path)

    def test_success_events_require_exact_skill_trace_and_official_predicate(self):
        events = self.make_events()
        result = validate_fastwam_events(events)
        self.assertEqual(result.terminal_status, "COMPLETED")
        verify_index = next(
            index
            for index, event in enumerate(events)
            if event.skill_id == "ARM-VER-01" and event.event_type == "skill_completed"
        )
        forged = list(events)
        forged[verify_index] = forged[verify_index].copy_with(
            state={"official_success": False}
        )
        with self.assertRaisesRegex(ValueError, "official_success"):
            validate_fastwam_events(forged)

    def test_failed_events_may_not_complete_verification(self):
        events = self.make_events(success=False)
        self.assertEqual(validate_fastwam_events(events).terminal_status, "FAILED")
        forged = list(events)
        terminal = forged.pop()
        forged.extend(
            [
                terminal.copy_with(
                    sequence=len(forged),
                    event_type="skill_completed",
                    status="RUNNING",
                    skill_id="ARM-VER-01",
                    state={"official_success": False},
                ),
                terminal.copy_with(sequence=len(forged) + 1),
            ]
        )
        with self.assertRaises(ValueError):
            validate_fastwam_events(forged)

    def test_package_binds_five_attempts_first_success_and_counts(self):
        events = self.make_events()
        actions = self.make_actions()
        summary = self.make_summary()
        result = validate_fastwam_package(summary, events, actions)
        self.assertEqual(result.terminal_status, "COMPLETED")
        for key, value in (
            ("selected_attempt", 3),
            ("attempt_count", 4),
            ("action_count", 3),
            ("frame_count", 1),
            ("policy_revision", "0" * 40),
            ("policy_weights_sha256", "0" * 64),
        ):
            forged = {**summary, key: value}
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_fastwam_package(forged, events, actions)

    def test_all_failed_package_requires_null_selection_and_failed_events(self):
        events = self.make_events(success=False)
        actions = self.make_actions()
        summary = self.make_summary(selected_attempt=-1)
        summary.update(
            {
                "event_count": len(events),
                "terminal_status": "FAILED",
                "official_success": False,
                "selected_attempt": None,
            }
        )
        self.assertEqual(
            validate_fastwam_package(summary, events, actions).terminal_status,
            "FAILED",
        )
        forged = {**summary, "selected_attempt": 0}
        with self.assertRaises(ValueError):
            validate_fastwam_package(forged, events, actions)


if __name__ == "__main__":
    unittest.main()
