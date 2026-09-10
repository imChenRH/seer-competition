import unittest
from unittest.mock import patch
from uuid import UUID

from seer_demo.feishu import FeishuApiError, FeishuClient, FeishuSettings
from seer_demo.bridge import TaskRecord
from seer_demo.contracts import Event


class RecordingFeishuClient(FeishuClient):
    def __init__(self, responses):
        super().__init__(FeishuSettings("id", "secret", "token", "tasks"))
        self.responses = list(responses)
        self.calls = []

    def _request(self, method, url, payload=None, auth=True, response_at_root=False):
        self.calls.append((method, url, payload))
        return self.responses.pop(0)


class FeishuFieldTests(unittest.TestCase):
    @staticmethod
    def task_record(checkpoint):
        return {
            "record_id": "rec-1",
            "fields": {
                "任务ID": "T-1",
                "原始指令": "卸载3号集装箱货物到A区传送带",
                "技能序列": (
                    "FORK-NAV-01→FORK-NAV-03→FORK-PER-01→FORK-OP-01→"
                    "FORK-OP-02→FORK-OP-03→FORK-NAV-02→FORK-OP-05→FORK-OP-04"
                ),
                "任务状态": "执行中",
                "最后事件序号": checkpoint,
            },
        }

    def test_audit_append_uses_stable_uuid4_client_token(self):
        client = RecordingFeishuClient([{}, {}])
        client.settings = FeishuSettings("id", "secret", "token", "tasks", "audit")
        task = TaskRecord("rec", "T-1", "normal", "instruction", (), "执行中")
        event = Event(
            schema_version="1.0",
            run_id="run-1",
            sequence=7,
            scenario="normal",
            event_type="skill_completed",
            source="isaac_sim",
            sim_time_s=10.0,
            status="RUNNING",
            occurred_at="2026-08-13T00:00:00+00:00",
            message="done",
        )

        client.append_audit(task, event)
        client.append_audit(task, event)

        urls = [call[1] for call in client.calls]
        self.assertEqual(urls[0], urls[1])
        token = urls[0].split("client_token=", 1)[1]
        parsed = UUID(token)
        self.assertEqual(parsed.version, 4)

    def test_waiting_task_pagination_uses_query_parameters(self):
        client = RecordingFeishuClient(
            [
                {"items": [], "has_more": True, "page_token": "next-token"},
                {"items": [], "has_more": False},
            ]
        )

        self.assertEqual(client.list_waiting_tasks(), [])

        self.assertTrue(client.calls[0][1].endswith("/records/search?page_size=100"))
        self.assertTrue(
            client.calls[1][1].endswith("/records/search?page_size=100&page_token=next-token")
        )
        self.assertNotIn("page_size", client.calls[0][2])
        self.assertNotIn("page_token", client.calls[1][2])
        conditions = client.calls[0][2]["filter"]["conditions"]
        self.assertNotIn("任务状态", [condition["field_name"] for condition in conditions])

    def test_try_claim_resumes_same_owned_in_progress_task(self):
        marker = "CLAIMED:bridge-a:T-1"
        client = RecordingFeishuClient(
            [
                {
                    "record": {
                        "fields": {
                            "任务状态": "执行中",
                            "外部执行状态": marker + "|run-1#7:skill_completed",
                        }
                    }
                }
            ]
        )

        claimed = client.try_claim("rec-1", "bridge-a:T-1")

        self.assertTrue(claimed)
        self.assertEqual([call[0] for call in client.calls], ["GET"])

    def test_get_token_reads_feishu_root_response_envelope(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"code":0,"msg":"success","tenant_access_token":"tenant-token","expire":7200}'

        client = FeishuClient(FeishuSettings("id", "secret", "token", "tasks"))

        with patch("seer_demo.feishu.urlopen", return_value=Response()):
            token = client._get_token()

        self.assertEqual(token, "tenant-token")

    def test_ensure_number_field_reuses_existing_numeric_field(self):
        client = RecordingFeishuClient(
            [{"items": [{"field_id": "fld-sequence", "field_name": "最后事件序号", "type": 2}]}]
        )

        field_id = client.ensure_number_field("tasks", "最后事件序号")

        self.assertEqual(field_id, "fld-sequence")
        self.assertEqual([call[0] for call in client.calls], ["GET"])

    def test_ensure_number_field_creates_integer_field_when_absent(self):
        client = RecordingFeishuClient(
            [
                {"items": [{"field_id": "fld-title", "field_name": "任务ID", "type": 1}]},
                {"field": {"field_id": "fld-new", "field_name": "最后事件序号", "type": 2}},
            ]
        )

        field_id = client.ensure_number_field("tasks", "最后事件序号")

        self.assertEqual(field_id, "fld-new")
        self.assertEqual(client.calls[1][0], "POST")
        self.assertEqual(
            client.calls[1][2],
            {"field_name": "最后事件序号", "type": 2, "property": {"formatter": "0"}},
        )

    def test_ensure_number_field_rejects_same_name_with_wrong_type(self):
        client = RecordingFeishuClient(
            [{"items": [{"field_id": "fld-text", "field_name": "最后事件序号", "type": 1}]}]
        )

        with self.assertRaisesRegex(FeishuApiError, "must be numeric"):
            client.ensure_number_field("tasks", "最后事件序号")

    def test_checkpoint_zero_is_preserved_exactly(self):
        client = RecordingFeishuClient([])

        task = client._parse_task(self.task_record(0))

        self.assertEqual(task.last_event_sequence, 0)

    def test_checkpoint_rejects_float_and_boolean_values(self):
        client = RecordingFeishuClient([])

        for invalid in (1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(FeishuApiError, "最后事件序号.*integer"):
                    client._parse_task(self.task_record(invalid))


if __name__ == "__main__":
    unittest.main()
