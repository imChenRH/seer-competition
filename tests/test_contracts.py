import json
import math
import tempfile
import unittest
from pathlib import Path

from seer_demo.contracts import (
    EventWriter,
    load_events,
    validate_events,
    validate_scenario_events,
)


class EventContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "run.jsonl"

    def make_valid_run(self):
        with EventWriter(
            self.path,
            run_id="run-normal-001",
            scenario="normal",
            source="dry_run",
        ) as writer:
            writer.emit("task_started", 0.0, status="RUNNING", message="start")
            writer.emit(
                "skill_completed",
                1.0,
                skill_id="FORK-NAV-01",
                status="RUNNING",
                state={"base_x_m": 1.0},
                evidence={"observed": True},
            )
            writer.emit("task_completed", 2.0, status="COMPLETED", message="done")
        return load_events(self.path)

    @staticmethod
    def as_isaac(events):
        decision_types = {
            "skill_completed",
            "skill_failed",
            "fallback_completed",
            "safety_stop",
            "task_completed",
            "human_intervention_requested",
        }
        observed_frame = 0
        converted = []
        for event in events:
            if event.event_type in decision_types:
                if event.event_type not in {
                    "task_completed",
                    "human_intervention_requested",
                }:
                    observed_frame = event.sequence
                converted.append(
                    event.copy_with(
                        source="isaac_sim",
                        evidence={
                            **event.evidence,
                            "stage_observed": True,
                            "observed_frame": observed_frame,
                        },
                    )
                )
            else:
                converted.append(event.copy_with(source="isaac_sim"))
        return converted

    def test_valid_run_round_trips_as_contiguous_jsonl(self):
        events = self.make_valid_run()

        result = validate_events(events, expected_scenario="normal")

        self.assertEqual(result.run_id, "run-normal-001")
        self.assertEqual(result.terminal_status, "COMPLETED")
        self.assertEqual([event.sequence for event in events], [0, 1, 2])
        self.assertEqual(json.loads(self.path.read_text().splitlines()[1])["skill_id"], "FORK-NAV-01")

    def test_rejects_sequence_gap(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(sequence=4)

        with self.assertRaisesRegex(ValueError, "sequence.*expected 1"):
            validate_events(events)

    def test_rejects_simulation_time_regression(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(sim_time_s=-0.1)

        with self.assertRaisesRegex(ValueError, "sim_time_s.*monotonic"):
            validate_events(events)

    def test_rejects_mixed_run_ids(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(run_id="other-run")

        with self.assertRaisesRegex(ValueError, "run_id"):
            validate_events(events)

    def test_rejects_mixed_sources(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(source="isaac_sim")

        with self.assertRaisesRegex(ValueError, "source changed"):
            validate_events(events)

    def test_rejects_terminal_event_with_wrong_status(self):
        events = self.make_valid_run()
        events[-1] = events[-1].copy_with(status="FAILED")

        with self.assertRaisesRegex(ValueError, "task_completed.*COMPLETED"):
            validate_events(events)

    def test_rejects_more_than_one_terminal_event(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(event_type="task_failed", status="FAILED")

        with self.assertRaisesRegex(ValueError, "terminal.*last"):
            validate_events(events)

    def test_rejects_event_after_terminal(self):
        events = self.make_valid_run()
        events[1] = events[1].copy_with(event_type="task_completed", status="COMPLETED")

        with self.assertRaisesRegex(ValueError, "terminal.*last"):
            validate_events(events)

    def test_rejects_unknown_source(self):
        with self.assertRaisesRegex(ValueError, "source"):
            EventWriter(self.path, "run-1", "normal", "pretend_sim")

    def test_load_rejects_malformed_jsonl_with_line_number(self):
        with EventWriter(self.path, "run-1", "normal", "dry_run") as writer:
            writer.emit("task_started", 0.0, status="RUNNING")
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("not-json\n")

        with self.assertRaisesRegex(ValueError, "line 2"):
            load_events(self.path)

    def test_load_rejects_unknown_fields_and_wrong_scalar_types(self):
        with EventWriter(self.path, "run-1", "normal", "dry_run") as writer:
            writer.emit("task_started", 0.0, status="RUNNING")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        document["invented"] = "must not be ignored"
        self.path.write_text(json.dumps(document) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unknown fields.*invented"):
            load_events(self.path)

        document.pop("invented")
        document["run_id"] = 123
        self.path.write_text(json.dumps(document) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "run_id must be a non-empty string"):
            load_events(self.path)

    def test_rejects_nonfinite_time_and_malformed_timestamp(self):
        valid = self.make_valid_run()
        events = list(valid)
        events[1] = events[1].copy_with(sim_time_s=math.nan)
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_events(events)

        events = list(valid)
        events[1] = events[1].copy_with(occurred_at="not-a-timestamp")
        with self.assertRaisesRegex(ValueError, "occurred_at"):
            validate_events(events)

    def test_event_writer_refuses_to_overwrite_existing_evidence(self):
        self.path.write_text("existing evidence\n", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            with EventWriter(self.path, "run-new", "normal", "dry_run"):
                pass

    def test_scenario_validation_rejects_truncated_normal_success(self):
        events = self.make_valid_run()

        with self.assertRaisesRegex(ValueError, "event trace mismatch"):
            validate_scenario_events(events, expected_scenario="normal")

    def test_scenario_validation_rejects_completed_skill_with_failed_state_predicate(self):
        with EventWriter(self.path, "run-normal-full", "normal", "dry_run") as writer:
            from seer_demo.backends.dry_run import DryRunBackend
            from seer_demo.engine import DemoEngine

            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        events = load_events(self.path)
        index = next(
            i
            for i, event in enumerate(events)
            if event.event_type == "skill_completed" and event.skill_id == "FORK-OP-01"
        )
        events[index] = events[index].copy_with(
            state={**events[index].state, "payload_attached": False}
        )

        with self.assertRaisesRegex(ValueError, "FORK-OP-01.*observed state predicate"):
            validate_scenario_events(events, expected_scenario="normal")

    def test_scenario_validation_rejects_reordered_started_and_completed_events(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        with EventWriter(self.path, "run-normal-order", "normal", "dry_run") as writer:
            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        events = load_events(self.path)
        started, completed = events[1], events[2]
        events[1], events[2] = (
            completed.copy_with(
                sequence=1,
                sim_time_s=started.sim_time_s,
                occurred_at=started.occurred_at,
            ),
            started.copy_with(
                sequence=2,
                sim_time_s=completed.sim_time_s,
                occurred_at=completed.occurred_at,
            ),
        )

        with self.assertRaisesRegex(ValueError, "event trace mismatch"):
            validate_scenario_events(events, expected_scenario="normal")

    def test_scenario_validation_rejects_forged_fallback_and_terminal_observations(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        with EventWriter(self.path, "run-recovery-forged", "recovery", "dry_run") as writer:
            DemoEngine(DryRunBackend("recovery"), writer).run("recovery")
        events = load_events(self.path)
        fallback_index = next(
            i for i, event in enumerate(events) if event.event_type == "fallback_completed"
        )
        events[fallback_index] = events[fallback_index].copy_with(
            state={**events[fallback_index].state, "pallet_lateral_error_m": 0.20}
        )
        with self.assertRaisesRegex(ValueError, "FB-F01.*observed state predicate"):
            validate_scenario_events(events, expected_scenario="recovery")

        intervention_path = self.path.with_name("intervention.jsonl")
        with EventWriter(
            intervention_path, "run-intervention-forged", "intervention", "dry_run"
        ) as writer:
            DemoEngine(DryRunBackend("intervention"), writer).run("intervention")
        events = load_events(intervention_path)
        events[-1] = events[-1].copy_with(
            state={**events[-1].state, "safe_retreat_complete": False}
        )
        with self.assertRaisesRegex(ValueError, "terminal state"):
            validate_scenario_events(events, expected_scenario="intervention")

    def test_scenario_validation_rejects_forged_expected_failures_and_missing_perception_fields(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        recovery_path = self.path.with_name("recovery.jsonl")
        with EventWriter(recovery_path, "run-recovery-failure", "recovery", "dry_run") as writer:
            DemoEngine(DryRunBackend("recovery"), writer).run("recovery")
        recovery = load_events(recovery_path)
        failed_index = next(i for i, e in enumerate(recovery) if e.event_type == "skill_failed")
        recovery[failed_index] = recovery[failed_index].copy_with(
            state={**recovery[failed_index].state, "pallet_lateral_error_m": 0.0}
        )
        with self.assertRaisesRegex(ValueError, "expected failure predicate"):
            validate_scenario_events(recovery, expected_scenario="recovery")

        intervention_path = self.path.with_name("intervention-failures.jsonl")
        with EventWriter(
            intervention_path, "run-intervention-failures", "intervention", "dry_run"
        ) as writer:
            DemoEngine(DryRunBackend("intervention"), writer).run("intervention")
        intervention = load_events(intervention_path)
        failed_index = next(i for i, e in enumerate(intervention) if e.event_type == "skill_failed")
        intervention[failed_index] = intervention[failed_index].copy_with(
            state={**intervention[failed_index].state, "obstacle_visible": False}
        )
        with self.assertRaisesRegex(ValueError, "expected failure predicate"):
            validate_scenario_events(intervention, expected_scenario="intervention")

        normal_path = self.path.with_name("normal-missing-fields.jsonl")
        with EventWriter(normal_path, "run-normal-missing", "normal", "dry_run") as writer:
            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        normal = load_events(normal_path)
        perception_index = next(
            i
            for i, e in enumerate(normal)
            if e.event_type == "skill_completed" and e.skill_id == "FORK-PER-01"
        )
        normal[perception_index] = normal[perception_index].copy_with(
            state={"unrelated": True}
        )
        with self.assertRaisesRegex(ValueError, "observed state predicate"):
            validate_scenario_events(normal, expected_scenario="normal")

    def test_scenario_validation_rejects_wrong_attempts_or_missing_isaac_observation_frame(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        with EventWriter(self.path, "run-attempts", "recovery", "dry_run") as writer:
            DemoEngine(DryRunBackend("recovery"), writer).run("recovery")
        events = load_events(self.path)
        failed_index = next(i for i, e in enumerate(events) if e.event_type == "skill_failed")
        events[failed_index] = events[failed_index].copy_with(
            evidence={**events[failed_index].evidence, "attempt": 2}
        )
        with self.assertRaisesRegex(ValueError, "attempt"):
            validate_scenario_events(events, expected_scenario="recovery")

        isaac = [
            event.copy_with(
                source="isaac_sim",
                evidence={**event.evidence, "stage_observed": True, "observed_frame": event.sequence},
            )
            if event.event_type in {"skill_completed", "skill_failed", "fallback_completed", "safety_stop"}
            else event.copy_with(source="isaac_sim")
            for event in load_events(self.path)
        ]
        isaac[failed_index] = isaac[failed_index].copy_with(
            evidence={**isaac[failed_index].evidence, "observed_frame": None}
        )
        with self.assertRaisesRegex(ValueError, "observed_frame"):
            validate_scenario_events(isaac, expected_scenario="recovery")

    def test_scenario_validation_rejects_unobserved_or_forged_isaac_terminal(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        with EventWriter(self.path, "run-terminal", "normal", "dry_run") as writer:
            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        isaac = self.as_isaac(load_events(self.path))

        missing_observation = list(isaac)
        missing_observation[-1] = missing_observation[-1].copy_with(
            evidence={"completed_skill_count": 9}
        )
        with self.assertRaisesRegex(ValueError, "task_completed.*stage observation"):
            validate_scenario_events(missing_observation, expected_scenario="normal")

        forged_state = list(isaac)
        forged_state[-1] = forged_state[-1].copy_with(
            state={**forged_state[-1].state, "base_x_m": 999.0, "payload_x_m": 999.0}
        )
        with self.assertRaisesRegex(ValueError, "terminal observation.*preceding decision"):
            validate_scenario_events(forged_state, expected_scenario="normal")

    def test_scenario_validation_rejects_stopped_flag_with_nonzero_speed(self):
        from seer_demo.backends.dry_run import DryRunBackend
        from seer_demo.engine import DemoEngine

        with EventWriter(
            self.path, "run-stop-speed", "intervention", "dry_run"
        ) as writer:
            DemoEngine(DryRunBackend("intervention"), writer).run("intervention")
        isaac = self.as_isaac(load_events(self.path))
        stop_index = next(i for i, event in enumerate(isaac) if event.event_type == "safety_stop")
        contradictory_state = {**isaac[stop_index].state, "base_speed_mps": 99.0}
        isaac[stop_index] = isaac[stop_index].copy_with(state=contradictory_state)
        isaac[-1] = isaac[-1].copy_with(state=contradictory_state)

        with self.assertRaisesRegex(ValueError, "base_speed_mps"):
            validate_scenario_events(isaac, expected_scenario="intervention")


if __name__ == "__main__":
    unittest.main()
