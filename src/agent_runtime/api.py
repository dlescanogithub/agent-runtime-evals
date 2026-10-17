"""Small JSON API for the human gate.

Every route except GET /health requires Authorization: Bearer <API_TOKEN>.
The compare is constant-time on SHA-256 digests. The token is never logged.
Bind stays on localhost. This is not a substitute for the customer's identity
provider. See the runbook.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent_runtime.cli import outcome_dict
from agent_runtime.config import Config
from agent_runtime.errors import AgentRuntimeError, ConfigError
from agent_runtime.jsonutil import as_dict, dumps, loads
from agent_runtime.logging_setup import log
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.runner import AgentRunner
from agent_runtime.store import SQLiteStore
from agent_runtime.wiring import build_runner

logger = logging.getLogger("agent_runtime.api")

_UNAUTHORIZED: dict[str, object] = {
    "error": {"code": "unauthorized", "message": "Bearer token required"}
}


def bearer_matches(header: str | None, expected: str) -> bool:
    """Compare a Bearer token without leaking it through an early length check.

    Hashing both sides makes the compare a fixed length. An empty expected
    token never matches, so a server started without API_TOKEN stays closed.
    """

    if not expected:
        return False
    presented = ""
    prefix = "Bearer "
    if header is not None and header.startswith(prefix):
        presented = header[len(prefix) :]
    actual = hashlib.sha256(presented.encode("utf-8")).digest()
    wanted = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(actual, wanted)


class AppServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        runner: AgentRunner,
        store: SQLiteStore,
        api_token: str,
    ) -> None:
        super().__init__(address, Handler)
        self.runner = runner
        self.app_store = store
        self.api_token = api_token


class Handler(BaseHTTPRequestHandler):
    def _app(self) -> AppServer:
        if isinstance(self.server, AppServer):
            return self.server
        raise RuntimeError("API handler is not bound to AppServer")

    def log_message(self, format: str, *args: object) -> None:
        # The default logger writes the request line. Our logs stay structured.
        del format, args

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        app = self._app()
        if path == "/health":
            self._send(200, {"provider": app.runner.provider_name, "status": "ok"})
            return
        if not self._authorized():
            self._send(401, _UNAUTHORIZED)
            return
        parts = [part for part in path.split("/") if part]
        if len(parts) == 2 and parts[0] == "runs":
            try:
                run = app.app_store.get_run(parts[1])
            except AgentRuntimeError as exc:
                self._send(404, {"error": {"code": "not_found", "message": str(exc)}})
                return
            steps = app.app_store.list_steps(run.id)
            self._send(
                200,
                {
                    "error": run.error,
                    "run_id": run.id,
                    "status": run.status,
                    "steps": [step.name for step in steps],
                },
            )
            return
        self._send(404, {"error": {"code": "not_found", "message": "unknown path"}})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, _UNAUTHORIZED)
            return
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        app = self._app()
        try:
            if parts == ["runs"]:
                body = self._body()
                outcome = app.runner.start(body)
                self._send(200, outcome_dict(outcome))
                return
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "resume":
                outcome = app.runner.resume(parts[1])
                self._send(200, outcome_dict(outcome))
                return
            if (
                len(parts) == 5
                and parts[0] == "runs"
                and parts[2] == "steps"
                and parts[4] in ("approve", "reject")
            ):
                reason = ""
                if parts[4] == "reject":
                    raw = self._body()
                    reason_value = raw.get("reason")
                    reason = reason_value if isinstance(reason_value, str) else ""
                app.runner.decide(parts[1], parts[3], parts[4], reason)
                outcome = app.runner.resume(parts[1])
                self._send(200, outcome_dict(outcome))
                return
        except AgentRuntimeError as exc:
            self._send(400, {"error": {"code": "rejected", "message": str(exc)}})
            return
        self._send(404, {"error": {"code": "not_found", "message": "unknown path"}})

    def _authorized(self) -> bool:
        return bearer_matches(self.headers.get("Authorization"), self._app().api_token)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return as_dict(loads(raw))

    def _send(self, status: int, payload: dict[str, object]) -> None:
        encoded = dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _require_token(config: Config) -> str:
    if not config.api_token:
        raise ConfigError("API_TOKEN is required to serve the API")
    return config.api_token


def serve(config: Config) -> None:
    token = _require_token(config)
    runner = build_runner(
        config, provider=FakeProvider() if config.llm_provider == "fake" else None
    )
    store = SQLiteStore(config.database_path)
    server = AppServer((config.api_host, config.api_port), runner, store, token)
    log(logger, logging.INFO, "api_listening", host=config.api_host, port=config.api_port)
    server.serve_forever()


def bind(config: Config) -> AppServer:
    """Listen on an ephemeral port. Tests use this and close the server."""

    token = _require_token(config)
    runner = build_runner(config, provider=FakeProvider())
    store = SQLiteStore(config.database_path)
    return AppServer((config.api_host, 0), runner, store, token)


def port_of(server: AppServer) -> int:
    port = server.server_address[1]
    if not isinstance(port, int):
        raise RuntimeError("server address has no TCP port")
    return port
