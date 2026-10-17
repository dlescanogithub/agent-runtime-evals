"""One JSONL file per run.

Lines carry latency, tokens, and cost. They do not carry email addresses or
message bodies. Those stay in the local database. A trace file should be safe
to ship to a collector later without a second redaction pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class Tracer:
    def __init__(self, directory: Path, run_id: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{run_id}.jsonl"

    def emit(self, event: str, **fields: object) -> None:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
        }
        payload.update(fields)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
