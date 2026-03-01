from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from infra_agents.orchestrator import WorkflowSupervisor


class JobHandler(BaseHTTPRequestHandler):
    supervisor = WorkflowSupervisor()
    output_dir = Path("jobs")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/jobs":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length).decode("utf-8") if length else "{}"

        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
            return

        prompt = body.get("prompt", "")
        if not prompt.strip():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "prompt is required"})
            return

        state = self.supervisor.run(
            prompt=prompt,
            output_root=self.output_dir,
            execution_mode="plan-only",
        )
        self._send_json(
            HTTPStatus.OK,
            {
                "job_id": state.job_id,
                "status": state.status,
                "workspace": str(state.workspace),
                "summary_file": str(state.workspace / "summary.json"),
                "engine": self.supervisor.engine,
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), JobHandler)
    print("API ativa em http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
