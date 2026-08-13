"""Small Feishu Bitable boundary with no third-party runtime dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .bridge import TaskRecord
from .contracts import Event


class FeishuApiError(RuntimeError):
    pass


def load_env_file(path: Path | str) -> None:
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True, slots=True)
class FeishuSettings:
    app_id: str
    app_secret: str
    app_token: str
    tasks_table: str
    audit_table: str = ""
    timeout_s: float = 15.0

    @classmethod
    def from_environment(cls) -> "FeishuSettings":
        required = ("APP_ID", "APP_SECRET", "APP_TOKEN", "TABLE_TASKS")
        missing = [key for key in required if not os.environ.get(key)]
        if missing:
            raise ValueError(f"missing Feishu environment fields: {', '.join(missing)}")
        return cls(
            app_id=os.environ["APP_ID"],
            app_secret=os.environ["APP_SECRET"],
            app_token=os.environ["APP_TOKEN"],
            tasks_table=os.environ["TABLE_TASKS"],
            audit_table=os.environ.get("TABLE_AUDIT", ""),
            timeout_s=float(os.environ.get("FEISHU_TIMEOUT_S", "15")),
        )


class FeishuClient:
    def __init__(self, settings: FeishuSettings):
        self.settings = settings
        self._token = ""
        self._token_expiry = 0.0

    def _request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None = None,
        auth: bool = True,
        response_at_root: bool = False,
    ):
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self._get_token()}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.settings.timeout_s) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise FeishuApiError(f"Feishu request failed: {type(exc).__name__}") from exc
        if document.get("code") != 0:
            raise FeishuApiError(f"Feishu API error {document.get('code')}: {document.get('msg', '')}")
        return document if response_at_root else document.get("data", {})

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        data = self._request(
            "POST",
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.settings.app_id, "app_secret": self.settings.app_secret},
            auth=False,
            response_at_root=True,
        )
        self._token = data["tenant_access_token"]
        self._token_expiry = time.time() + float(data.get("expire", 7200))
        return self._token

    def _table_url(self, table: str, suffix: str) -> str:
        return (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.settings.app_token}"
            f"/tables/{table}{suffix}"
        )

    def list_fields(self, table: str) -> list[Mapping[str, Any]]:
        fields: list[Mapping[str, Any]] = []
        page_token = ""
        while True:
            query: dict[str, object] = {"page_size": 100}
            if page_token:
                query["page_token"] = page_token
            data = self._request(
                "GET",
                self._table_url(table, "/fields") + "?" + urlencode(query),
            )
            fields.extend(data.get("items", []))
            if not data.get("has_more"):
                return fields
            page_token = str(data.get("page_token", ""))
            if not page_token:
                raise FeishuApiError("field pagination indicated has_more without page_token")

    def ensure_number_field(self, table: str, field_name: str) -> str:
        for field in self.list_fields(table):
            if field.get("field_name") != field_name:
                continue
            if field.get("type") != 2:
                raise FeishuApiError(f"existing field {field_name!r} must be numeric")
            return str(field["field_id"])
        data = self._request(
            "POST",
            self._table_url(table, "/fields"),
            {"field_name": field_name, "type": 2, "property": {"formatter": "0"}},
        )
        field = data.get("field", {})
        if field.get("field_name") != field_name or field.get("type") != 2:
            raise FeishuApiError(f"Feishu did not create numeric field {field_name!r}")
        return str(field["field_id"])

    def list_waiting_tasks(self) -> list[TaskRecord]:
        records: list[TaskRecord] = []
        page_token = ""
        while True:
            payload: dict[str, Any] = {
                "filter": {
                    "conjunction": "and",
                    "conditions": [
                        {"field_name": "执行来源", "operator": "is", "value": ["sim"]},
                    ],
                },
            }
            query: dict[str, object] = {"page_size": 100}
            if page_token:
                query["page_token"] = page_token
            data = self._request(
                "POST",
                self._table_url(self.settings.tasks_table, "/records/search") + "?" + urlencode(query),
                payload,
            )
            records.extend(self._parse_task(item) for item in data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token", ""))
            if not page_token:
                raise FeishuApiError("pagination indicated has_more without page_token")
        return records

    def try_claim(self, record_id: str, claim_id: str) -> bool:
        current = self._request(
            "GET", self._table_url(self.settings.tasks_table, f"/records/{record_id}")
        )
        current_fields = current.get("record", {}).get("fields", {})
        current_status = self._field_text(current_fields.get("任务状态"))
        marker = f"CLAIMED:{claim_id}"
        external_status = self._field_text(current_fields.get("外部执行状态"))
        if current_status in {"执行中", "Fallback中"}:
            return external_status.startswith(marker + "|") or external_status == marker
        if current_status != "等待中":
            return False
        self.update_task(record_id, {"任务状态": "执行中", "外部执行状态": marker})
        confirmed = self._request(
            "GET", self._table_url(self.settings.tasks_table, f"/records/{record_id}")
        )
        fields = confirmed.get("record", {}).get("fields", {})
        return self._field_text(fields.get("任务状态")) == "执行中" and self._field_text(
            fields.get("外部执行状态")
        ) == marker

    def update_task(self, record_id: str, fields: Mapping[str, object]) -> None:
        self._request(
            "PUT",
            self._table_url(self.settings.tasks_table, f"/records/{record_id}"),
            {"fields": dict(fields)},
        )

    def append_audit(self, task: TaskRecord, event: Event) -> None:
        if not self.settings.audit_table:
            return
        event_name = {
            "task_started": "任务分解",
            "skill_started": "技能选择",
            "skill_completed": "验证通过",
            "skill_failed": "验证拦截",
            "fallback_started": "Fallback触发",
            "human_intervention_requested": "人工介入",
            "task_completed": "任务完成",
        }.get(event.event_type, "参数输出")
        token_bytes = hashlib.sha256(f"{event.run_id}:{event.sequence}".encode("utf-8")).digest()[:16]
        client_token = str(uuid.UUID(bytes=token_bytes, version=4))
        occurred_at_ms = int(datetime.fromisoformat(event.occurred_at).timestamp() * 1000)
        self._request(
            "POST",
            self._table_url(self.settings.audit_table, "/records")
            + "?"
            + urlencode({"client_token": client_token}),
            {
                "fields": {
                    "时间戳": occurred_at_ms,
                    "任务ID": task.task_id,
                    "审计层级": "安全验证层" if event.event_type in {"skill_failed", "safety_stop"} else "执行反馈层",
                    "事件类型": event_name,
                    "详细内容": f"#{event.sequence} {event.message}",
                    "置信度": event.evidence.get("confidence", 1.0),
                }
            },
        )

    def _parse_task(self, record: Mapping[str, Any]) -> TaskRecord:
        fields = record.get("fields", {})
        instruction = self._field_text(fields.get("原始指令"))
        sequence_text = self._field_text(fields.get("技能序列"))
        raw_checkpoint = fields.get("最后事件序号")
        if raw_checkpoint is None:
            checkpoint = -1
        elif isinstance(raw_checkpoint, int) and not isinstance(raw_checkpoint, bool):
            checkpoint = raw_checkpoint
        else:
            raise FeishuApiError("最后事件序号 must be an integer or null")
        scenario = "intervention" if "遮挡" in instruction else "recovery" if "2号" in instruction else "normal"
        return TaskRecord(
            record_id=str(record["record_id"]),
            task_id=self._field_text(fields.get("任务ID")),
            scenario=scenario,
            instruction=instruction,
            skill_sequence=tuple(item for item in re.split(r"(?:->|→|,|，|、|\s)+", sequence_text) if item),
            status=self._field_text(fields.get("任务状态")),
            last_event_sequence=checkpoint,
        )

    @staticmethod
    def _field_text(value: Any) -> str:
        if isinstance(value, list):
            return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
        if value is None:
            return ""
        return str(value)
