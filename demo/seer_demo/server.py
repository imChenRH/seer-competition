"""Read-only HTTP server for validated Demo evidence and the operator console."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .contracts import load_events, validate_scenario_events
from .fastwam.contracts import (
    FASTWAM_SOURCE,
    load_action_records,
    validate_fastwam_package,
)


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _available_declared_media(run_dir: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value or Path(value).name != value:
        return None
    if not (run_dir / value).is_file():
        return None
    return value


class EvidenceCatalog:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def list_runs(self) -> list[dict[str, object]]:
        if not self.root.is_dir():
            return []
        runs = []
        for candidate in self.root.iterdir():
            if not candidate.is_dir() or not RUN_ID_PATTERN.fullmatch(candidate.name):
                continue
            try:
                runs.append(self.get_summary(candidate.name))
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(runs, key=lambda item: str(item.get("generated_at", "")), reverse=True)

    def get_summary(self, run_id: str) -> dict[str, object]:
        run_dir = self._run_dir(run_id)
        summary_path = run_dir / "summary.json"
        events_path = run_dir / "events.jsonl"
        if not summary_path.is_file() or not events_path.is_file():
            raise FileNotFoundError(run_id)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary, dict):
            raise ValueError("summary must be an object")
        events = load_events(events_path)
        if summary.get("source") == FASTWAM_SOURCE:
            actions_path = self._declared_file(run_dir, summary.get("actions_file"))
            validation = validate_fastwam_package(
                summary, events, load_action_records(actions_path)
            )
        else:
            validation = validate_scenario_events(events)
        if validation.run_id != run_id:
            raise ValueError("evidence run_id must match its directory name")
        exact = {
            "run_id": validation.run_id,
            "scenario": validation.scenario,
            "source": validation.source,
            "event_count": validation.event_count,
            "terminal_status": validation.terminal_status,
            "duration_s": validation.duration_s,
        }
        for key, value in exact.items():
            if summary.get(key) != value:
                raise ValueError(f"summary field {key} does not match events")
        result = dict(summary)
        result["run_id"] = run_id
        result["has_video"] = _available_declared_media(
            run_dir, summary.get("video_file")
        ) is not None
        result["has_presentation"] = _available_declared_media(
            run_dir, summary.get("presentation_file")
        ) is not None
        return result

    def events_path(self, run_id: str) -> Path:
        self.get_summary(run_id)
        return self._run_dir(run_id) / "events.jsonl"

    def actions_path(self, run_id: str) -> Path:
        summary = self.get_summary(run_id)
        if summary.get("source") != FASTWAM_SOURCE:
            raise FileNotFoundError(run_id)
        return self._declared_file(self._run_dir(run_id), summary.get("actions_file"))

    def _fastwam_technical_validation(self) -> dict[str, object]:
        evidence_dir = self.root / "fastwam"
        log_path = evidence_dir / "validation.log"
        readme_path = evidence_dir / "README.md"
        boundary = (
            "仅证明本地 checkpoint 可加载到 CUDA 并完成一次单批推理；不证明已控制叉车、"
            "完成后训练、达到论文实时指标或接入本仿真闭环。"
        )
        if not log_path.is_file() or not readme_path.is_file():
            return {
                "available": False,
                "action_shape": None,
                "single_call_latency_s": None,
                "claim_boundary": boundary,
                "validation_log_sha256": None,
            }
        log = log_path.read_text(encoding="utf-8")
        shape_match = re.search(r"INFERENCE_OK, action: torch\.Size\(\[([^]]+)\]\)", log)
        latency_match = re.search(r"推理耗时\s+([0-9]+(?:\.[0-9]+)?)s", log)
        available = "MODEL_LOADED" in log and "ON_CUDA" in log and "VERIFY_DONE" in log
        return {
            "available": available,
            "action_shape": f"[{shape_match.group(1)}]" if available and shape_match else None,
            "single_call_latency_s": float(latency_match.group(1)) if available and latency_match else None,
            "claim_boundary": boundary,
            "validation_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        }

    def fastwam_summary(self) -> dict[str, object]:
        technical = self._fastwam_technical_validation()
        rollout = next(
            (item for item in self.list_runs() if item.get("source") == FASTWAM_SOURCE),
            None,
        )
        return {
            **technical,
            "technical_validation": technical,
            "rollout": rollout,
        }

    def media_path(self, run_id: str, filename: str) -> Path:
        summary = self.get_summary(run_id)
        if Path(filename).name != filename:
            raise FileNotFoundError(filename)
        declared = {
            value
            for value in (summary.get("video_file"), summary.get("presentation_file"))
            if isinstance(value, str) and Path(value).name == value
        }
        if filename not in declared:
            raise FileNotFoundError(filename)
        path = self._run_dir(run_id) / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path

    @staticmethod
    def _declared_file(run_dir: Path, value: object) -> Path:
        if not isinstance(value, str) or not value or Path(value).name != value:
            raise FileNotFoundError(str(value))
        path = run_dir / value
        if not path.is_file():
            raise FileNotFoundError(value)
        return path

    def _run_dir(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise FileNotFoundError(run_id)
        candidate = (self.root / run_id).resolve()
        if candidate.parent != self.root:
            raise FileNotFoundError(run_id)
        return candidate


def create_server(host: str, port: int, evidence_root: Path | str, web_root: Path | str):
    catalog = EvidenceCatalog(evidence_root)
    web = Path(web_root).resolve()
    asset_map = {
        "/": web / "index.html",
        "/assets/styles.css": web / "styles.css",
        "/assets/protocol.js": web / "protocol.js",
        "/assets/app.js": web / "app.js",
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "SeerEvidenceServer/1.0"

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            try:
                if path in asset_map:
                    return self._send_file(asset_map[path])
                if path == "/api/runs":
                    return self._send_json({"runs": catalog.list_runs()})
                if path == "/api/fastwam":
                    return self._send_json(catalog.fastwam_summary())
                match = re.fullmatch(r"/api/runs/([^/]+)(/(?:events|actions))?", path)
                if match:
                    run_id, suffix = match.groups()
                    if suffix == "/events":
                        return self._send_file(
                            catalog.events_path(run_id), "application/x-ndjson; charset=utf-8"
                        )
                    if suffix == "/actions":
                        return self._send_file(
                            catalog.actions_path(run_id), "application/x-ndjson; charset=utf-8"
                        )
                    return self._send_json(catalog.get_summary(run_id))
                match = re.fullmatch(r"/media/([^/]+)/([^/]+)", path)
                if match:
                    return self._send_file(catalog.media_path(*match.groups()), "video/mp4")
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                return self._not_found()
            return self._not_found()

        def _send_json(self, value):
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path, content_type: str | None = None):
            if not path.is_file():
                return self._not_found()
            file_size = path.stat().st_size
            guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if guessed in {"text/html", "text/css", "application/javascript", "text/javascript"}:
                guessed += "; charset=utf-8"
            range_header = self.headers.get("Range")
            status = 200
            start = 0
            end = file_size - 1
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    return
                start_text, end_text = match.groups()
                if start_text and end_text:
                    start, requested_end = int(start_text), int(end_text)
                    end = min(requested_end, file_size - 1)
                elif start_text:
                    start = int(start_text)
                    end = file_size - 1
                else:
                    suffix_length = int(end_text)
                    start = max(0, file_size - suffix_length)
                    end = file_size - 1
                if start >= file_size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", content_type or guessed)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if path.name == "index.html":
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'",
                )
            self.end_headers()
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _not_found(self):
            body = b'{"error":"not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return ThreadingHTTPServer((host, port), Handler)
