import json
import threading
from urllib.request import Request, urlopen

from agent_runtime.api import bind, port_of
from agent_runtime.demo import DEMO_INPUT


def test_api_approve_flow(config) -> None:
    server = bind(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = port_of(server)
    try:
        health = _get(port, "/health")
        assert health["status"] == "ok"
        started = _post(port, "/runs", DEMO_INPUT)
        assert started["status"] == "waiting_review"
        step_id = started["pending"][0]["step_id"]
        run_id = started["run_id"]
        approved = _post(port, f"/runs/{run_id}/steps/{step_id}/approve", {})
        assert approved["status"] in ("waiting_review", "completed")
        while approved["status"] == "waiting_review":
            step_id = approved["pending"][0]["step_id"]
            approved = _post(port, f"/runs/{run_id}/steps/{step_id}/approve", {})
        assert approved["status"] == "completed"
        assert approved["output"]["amount_cents"] == 4200
    finally:
        server.shutdown()
        server.server_close()


def _get(port: int, path: str) -> dict[str, object]:
    with urlopen(f"http://127.0.0.1:{port}{path}") as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


def _post(port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed
