import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_runtime.api import bind, port_of
from agent_runtime.demo import DEMO_INPUT

TOKEN = "local-test-token"


def test_health_does_not_need_a_token(config) -> None:
    server = bind(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        health = _get(port_of(server), "/health", token=None)
        assert health["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()


def test_other_routes_reject_a_missing_or_wrong_token(config) -> None:
    server = bind(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = port_of(server)
    try:
        assert _status(port, "/runs", token=None) == 401
        assert _status(port, "/runs", token="wrong-token") == 401
    finally:
        server.shutdown()
        server.server_close()


def test_api_approve_flow(config) -> None:
    server = bind(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = port_of(server)
    try:
        started = _post(port, "/runs", DEMO_INPUT)
        assert started["status"] == "waiting_review"
        pending = started["pending"]
        assert isinstance(pending, list)
        first = pending[0]
        assert isinstance(first, dict)
        step_id = first["step_id"]
        run_id = started["run_id"]
        approved = _post(port, f"/runs/{run_id}/steps/{step_id}/approve", {})
        assert approved["status"] in ("waiting_review", "completed")
        while approved["status"] == "waiting_review":
            pending = approved["pending"]
            assert isinstance(pending, list)
            nxt = pending[0]
            assert isinstance(nxt, dict)
            step_id = nxt["step_id"]
            approved = _post(port, f"/runs/{run_id}/steps/{step_id}/approve", {})
        assert approved["status"] == "completed"
        output = approved["output"]
        assert isinstance(output, dict)
        assert output["amount_cents"] == 4200
    finally:
        server.shutdown()
        server.server_close()


def _get(port: int, path: str, token: str | None) -> dict[str, object]:
    request = Request(f"http://127.0.0.1:{port}{path}", headers=_headers(token))
    with urlopen(request) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


def _post(port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(TOKEN),
        method="POST",
    )
    with urlopen(request) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


def _status(port: int, path: str, token: str | None) -> int:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=b"{}",
        headers=_headers(token),
        method="POST",
    )
    try:
        with urlopen(request) as response:
            return int(response.status)
    except HTTPError as exc:
        return exc.code


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers
