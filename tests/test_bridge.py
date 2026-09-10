import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seer_demo.backends.dry_run import DryRunBackend
from seer_demo.bridge import RunExecution, SubprocessRunner, TaskBridge, TaskRecord
from seer_demo.contracts import EventWriter, load_events
from seer_demo.engine import DemoEngine


class FakeFeishuClient:
    def __init__(self, tasks, claim_allowed=True):
        self.tasks = {task.record_id: task for task in tasks}
        self.claim_allowed = claim_allowed
        self.claims = []
        self.updates = []
        self.audits = []
        self.operations = []

    def list_waiting_tasks(self):
        return [
            task
            for task in self.tasks.values()
            if task.status in {"等待中", "执行中", "Fallback中"}
        ]

    def try_claim(self, record_id, claim_id):
        self.claims.append((record_id, claim_id))
        task = self.tasks[record_id]
        if not self.claim_allowed or task.status not in {"等待中", "执行中", "Fallback中"}:
            return False
        if task.status == "等待中":
            self.tasks[record_id] = task.copy_with(status="执行中")
        return True

    def update_task(self, record_id, fields):
        if "最后事件序号" in fields:
            self.operations.append(("update", fields["最后事件序号"]))
        self.updates.append((record_id, dict(fields)))
        task = self.tasks[record_id]
        changes = {}
        if "任务状态" in fields:
            changes["status"] = fields["任务状态"]
        if "最后事件序号" in fields:
            changes["last_event_sequence"] = fields["最后事件序号"]
        self.tasks[record_id] = task.copy_with(**changes)

    def append_audit(self, task, event):
        self.operations.append(("audit", event.sequence))
        self.audits.append((task.task_id, event.sequence, event.event_type))


class FakeRunner:
    def __init__(self, execution):
        self.execution = execution
        self.calls = []
        self.resume_calls = []

    def run(self, task):
        self.calls.append(task)
        return self.execution

    def resume(self, task):
        self.resume_calls.append(task)
        return self.execution


class TaskBridgeTests(unittest.TestCase):
    def make_task(self):
        return TaskRecord(
            record_id="rec-1",
            task_id="T-801",
            scenario="normal",
            instruction="卸载3号集装箱货物到A区传送带",
            skill_sequence=(
                "FORK-NAV-01",
                "FORK-NAV-03",
                "FORK-PER-01",
                "FORK-OP-01",
                "FORK-OP-02",
                "FORK-OP-03",
                "FORK-NAV-02",
                "FORK-OP-05",
                "FORK-OP-04",
            ),
            status="等待中",
            last_event_sequence=-1,
        )

    def make_valid_execution(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "events.jsonl"
        with EventWriter(path, "T-801-normal", "normal", "isaac_sim") as writer:
            DemoEngine(DryRunBackend("normal"), writer).run("normal")
        events = tuple(
            event.copy_with(
                evidence={
                    **event.evidence,
                    "stage_observed": True,
                    "observed_frame": (
                        event.sequence - 1
                        if event.event_type in {"task_completed", "human_intervention_requested"}
                        else event.sequence
                    ),
                }
            )
            if event.event_type
            in {
                "skill_completed",
                "skill_failed",
                "fallback_completed",
                "safety_stop",
                "task_completed",
                "human_intervention_requested",
            }
            else event
            for event in load_events(path)
        )
        return RunExecution(exit_code=0, events=events, error="")

    def test_nine_skill_task_invokes_runner_exactly_once(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(outcomes[0].terminal_status, "COMPLETED")
        event_updates = [fields for _, fields in client.updates if "最后事件序号" in fields]
        self.assertEqual(
            [fields["最后事件序号"] for fields in event_updates],
            list(range(len(runner.execution.events))),
        )
        self.assertEqual(client.tasks[task.record_id].status, "已完成")
        self.assertEqual(len(client.audits), len(runner.execution.events))
        self.assertEqual(
            client.operations,
            [item for sequence in range(len(runner.execution.events)) for item in (("audit", sequence), ("update", sequence))],
        )

    def test_second_poll_does_not_reexecute_completed_task(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())
        bridge = TaskBridge(client, runner, bridge_id="bridge-test")

        bridge.process_once()
        second = bridge.process_once()

        self.assertEqual(second, [])
        self.assertEqual(len(runner.calls), 1)

    def test_owned_in_progress_task_replays_completed_evidence_without_restarting_runner(self):
        task = self.make_task().copy_with(status="执行中", last_event_sequence=7)
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(runner.calls, [])
        self.assertEqual(len(runner.resume_calls), 1)
        self.assertEqual(outcomes[0].terminal_status, "COMPLETED")
        self.assertEqual([sequence for _, sequence, _ in client.audits], list(range(8, 20)))

    def test_in_progress_task_without_completed_evidence_fails_instead_of_restarting(self):
        class MissingCompletedEvidenceRunner(FakeRunner):
            def resume(self, task):
                self.resume_calls.append(task)
                return RunExecution(2, (), "completed execution receipt missing")

        task = self.make_task().copy_with(status="执行中", last_event_sequence=7)
        client = FakeFeishuClient([task])
        runner = MissingCompletedEvidenceRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(runner.calls, [])
        self.assertEqual(len(runner.resume_calls), 1)
        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("receipt missing", outcomes[0].message)

    def test_resume_rejects_checkpoint_outside_valid_event_range(self):
        task = self.make_task().copy_with(status="执行中", last_event_sequence=999)
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("checkpoint", outcomes[0].message)
        self.assertEqual(client.audits, [])
        self.assertEqual(client.tasks[task.record_id].status, "异常")

    def test_terminal_checkpoint_repairs_stale_task_status_without_duplicate_audit(self):
        task = self.make_task().copy_with(status="执行中", last_event_sequence=19)
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "COMPLETED")
        self.assertEqual(client.audits, [])
        self.assertEqual(client.tasks[task.record_id].status, "已完成")
        self.assertEqual(client.tasks[task.record_id].last_event_sequence, 19)

    def test_failed_claim_never_starts_runner(self):
        client = FakeFeishuClient([self.make_task()], claim_allowed=False)
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes, [])
        self.assertEqual(runner.calls, [])

    def test_wrong_task_skill_sequence_fails_before_runner(self):
        task = self.make_task().copy_with(skill_sequence=("FORK-NAV-01", "FORK-OP-04"))
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(runner.calls, [])
        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertEqual(client.tasks[task.record_id].status, "异常")
        self.assertIn("skill sequence", outcomes[0].message)

    def test_nonzero_runner_exit_marks_task_failed_without_completion(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        runner = FakeRunner(RunExecution(exit_code=7, events=(), error="Isaac exited 7"))

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertEqual(client.tasks[task.record_id].status, "异常")
        self.assertNotIn("任务完成", [fields.get("外部执行状态") for _, fields in client.updates])

    def test_invalid_event_sequence_fails_closed(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        valid = self.make_valid_execution()
        broken = list(valid.events)
        broken[2] = broken[2].copy_with(sequence=99)
        runner = FakeRunner(RunExecution(exit_code=0, events=tuple(broken), error=""))

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertEqual(client.tasks[task.record_id].status, "异常")
        self.assertEqual(client.audits, [])

    def test_runner_evidence_must_belong_to_claimed_task(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        valid = self.make_valid_execution()
        stale = tuple(event.copy_with(run_id="T-OTHER-normal") for event in valid.events)
        runner = FakeRunner(RunExecution(exit_code=0, events=stale, error=""))

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("run_id", outcomes[0].message)
        self.assertEqual(client.audits, [])

    def test_runner_evidence_must_come_from_isaac(self):
        task = self.make_task()
        client = FakeFeishuClient([task])
        valid = self.make_valid_execution()
        dry = tuple(event.copy_with(source="dry_run") for event in valid.events)
        runner = FakeRunner(RunExecution(exit_code=0, events=dry, error=""))

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("source", outcomes[0].message)
        self.assertEqual(client.audits, [])

    def test_unsafe_task_id_fails_without_starting_runner(self):
        task = self.make_task().copy_with(task_id="../outside")
        client = FakeFeishuClient([task])
        runner = FakeRunner(self.make_valid_execution())

        outcomes = TaskBridge(client, runner, bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("task_id", outcomes[0].message)
        self.assertEqual(runner.calls, [])

    def test_runner_exception_marks_task_failed_instead_of_stopping_bridge(self):
        class RaisingRunner:
            def run(self, task):
                raise RuntimeError("backend transport disappeared")

        task = self.make_task()
        client = FakeFeishuClient([task])

        outcomes = TaskBridge(client, RaisingRunner(), bridge_id="bridge-test").process_once()

        self.assertEqual(outcomes[0].terminal_status, "FAILED")
        self.assertIn("runner raised RuntimeError", outcomes[0].message)
        self.assertEqual(client.tasks[task.record_id].status, "异常")

    def test_subprocess_timeout_becomes_failed_execution(self):
        task = self.make_task()
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = SubprocessRunner(("isaac-python",), temp_dir)
            with patch(
                "seer_demo.bridge.subprocess.run",
                side_effect=subprocess.TimeoutExpired(("isaac-python",), 900),
            ):
                execution = runner.run(task)

        self.assertEqual(execution.exit_code, 124)
        self.assertEqual(execution.events, ())
        self.assertIn("timed out", execution.error)

    def test_zero_exit_runner_cannot_replay_stale_events(self):
        task = self.make_task()
        with tempfile.TemporaryDirectory() as temp_dir:
            stale_dir = Path(temp_dir) / task.task_id
            stale_dir.mkdir()
            stale_path = stale_dir / "events.jsonl"
            with EventWriter(stale_path, "T-801-normal", "normal", "isaac_sim") as writer:
                DemoEngine(DryRunBackend("normal"), writer).run("normal")
            runner = SubprocessRunner(("isaac-python",), temp_dir)
            with patch("seer_demo.bridge.subprocess.run") as process:
                execution = runner.run(task)

        self.assertNotEqual(execution.exit_code, 0)
        self.assertEqual(execution.events, ())
        self.assertIn("already exists", execution.error)
        process.assert_not_called()

    def test_subprocess_runner_seals_complete_artifacts_and_resume_verifies_hashes(self):
        task = self.make_task()
        valid = self.make_valid_execution()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = SubprocessRunner(("isaac-python",), root)

            def completed_process(command, **kwargs):
                output_dir = Path(command[command.index("--output-dir") + 1])
                (output_dir / "events.jsonl").write_text(
                    "".join(
                        json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                        for event in valid.events
                    ),
                    encoding="utf-8",
                )
                summary = {
                    "run_id": "T-801-normal",
                    "scenario": "normal",
                    "source": "isaac_sim",
                    "event_count": 20,
                    "terminal_status": "COMPLETED",
                    "duration_s": 51.0,
                }
                (output_dir / "summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
                (output_dir / "scene.usda").write_text("#usda 1.0\n", encoding="utf-8")
                (output_dir / "simulation.mp4").write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("seer_demo.bridge.subprocess.run", side_effect=completed_process):
                execution = runner.run(task)

            self.assertEqual(execution.exit_code, 0, execution.error)
            receipt = root / task.task_id / ".runner-complete.json"
            self.assertTrue(receipt.is_file())
            resumed = runner.resume(task)
            self.assertEqual(resumed.exit_code, 0, resumed.error)

            (root / task.task_id / "scene.usda").write_text(
                "#usda 1.0\n# tampered\n", encoding="utf-8"
            )
            rejected = runner.resume(task)
            self.assertNotEqual(rejected.exit_code, 0)
            self.assertIn("hashes disagree", rejected.error)


if __name__ == "__main__":
    unittest.main()
