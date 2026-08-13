"""Read-only HTTP server for validated Demo evidence and the operator console."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .contracts import load_events, validate_scenario_events


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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
        validation = validate_scenario_events(load_events(events_path))
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
        result["has_video"] = (run_dir / "simulation.mp4").is_file() and summary.get(
            "video_file"
        ) == "simulation.mp4"
        return result

    def events_path(self, run_id: str) -> Path:
        self.get_summary(run_id)
        return self._run_dir(run_id) / "events.jsonl"

    def media_path(self, run_id: str, filename: str) -> Path:
        summary = self.get_summary(run_id)
        if filename != "simulation.mp4" or summary.get("video_file") != filename:
            raise FileNotFoundError(filename)
        path = self._run_dir(run_id) / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
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
                match = re.fullmatch(r"/api/runs/([^/]+)(/events)?", path)
                if match:
                    run_id, events_suffix = match.groups()
                    if events_suffix:
                        return self._send_file(
                            catalog.events_path(run_id), "application/x-ndjson; charset=utf-8"
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
            body = path.read_bytes()
            guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if guessed in {"text/html", "text/css", "application/javascript", "text/javascript"}:
                guessed += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type or guessed)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if path.name == "index.html":
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'",
                )
            self.end_headers()
            self.wfile.write(body)

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
