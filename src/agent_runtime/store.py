"""SQLite ledger for runs, steps, and external effects.

One connection per operation keeps the API server thread-safe. Production
would swap this module for Postgres and claim work with FOR UPDATE SKIP LOCKED.
The row shape is meant to survive that swap. See ADR 0001.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_runtime.errors import StoreError
from agent_runtime.jsonutil import as_dict, dumps, loads
from agent_runtime.types import (
    RunRecord,
    StepKind,
    StepRecord,
    StepStatus,
    require_run_status,
    require_step_kind,
    require_step_status,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    budget_micro_usd INTEGER NOT NULL,
    spent_micro_usd INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    idempotency_key TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    latency_us INTEGER,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_micro_usd INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (run_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_steps_run_seq ON steps(run_id, seq);

CREATE TABLE IF NOT EXISTS effects (
    idempotency_key TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refund_ledger (
    order_id TEXT PRIMARY KEY,
    refunded_cents INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class NewStep:
    run_id: str
    kind: StepKind
    name: str
    status: StepStatus
    input_json: str
    idempotency_key: str
    max_attempts: int
    output_json: str | None = None
    attempt: int = 0
    latency_us: int | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_micro_usd: int = 0
    error: str | None = None


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_run(self, input_json: str, budget_micro_usd: int) -> RunRecord:
        now = utc_now()
        run = RunRecord(
            id=str(uuid.uuid4()),
            status="running",
            input_json=input_json,
            output_json=None,
            budget_micro_usd=budget_micro_usd,
            spent_micro_usd=0,
            consecutive_failures=0,
            created_at=now,
            updated_at=now,
            error=None,
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, status, input_json, output_json, budget_micro_usd,
                    spent_micro_usd, consecutive_failures, created_at, updated_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.status,
                    run.input_json,
                    run.output_json,
                    run.budget_micro_usd,
                    run.spent_micro_usd,
                    run.consecutive_failures,
                    run.created_at,
                    run.updated_at,
                    run.error,
                ),
            )
        return run

    def get_run(self, run_id: str) -> RunRecord:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise StoreError(f"run not found: {run_id}")
        return _run_from_row(row)

    def save_run(self, run: RunRecord) -> RunRecord:
        updated = RunRecord(
            id=run.id,
            status=run.status,
            input_json=run.input_json,
            output_json=run.output_json,
            budget_micro_usd=run.budget_micro_usd,
            spent_micro_usd=run.spent_micro_usd,
            consecutive_failures=run.consecutive_failures,
            created_at=run.created_at,
            updated_at=utc_now(),
            error=run.error,
        )
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE runs SET
                    status = ?, output_json = ?, budget_micro_usd = ?,
                    spent_micro_usd = ?, consecutive_failures = ?, updated_at = ?, error = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    updated.output_json,
                    updated.budget_micro_usd,
                    updated.spent_micro_usd,
                    updated.consecutive_failures,
                    updated.updated_at,
                    updated.error,
                    updated.id,
                ),
            )
            if cursor.rowcount != 1:
                raise StoreError(f"run not found: {run.id}")
        return updated

    def insert_step(self, step: NewStep) -> StepRecord:
        now = utc_now()
        record = StepRecord(
            id=str(uuid.uuid4()),
            run_id=step.run_id,
            seq=0,
            kind=step.kind,
            name=step.name,
            status=step.status,
            input_json=step.input_json,
            output_json=step.output_json,
            idempotency_key=step.idempotency_key,
            attempt=step.attempt,
            max_attempts=step.max_attempts,
            latency_us=step.latency_us,
            tokens_in=step.tokens_in,
            tokens_out=step.tokens_out,
            cost_micro_usd=step.cost_micro_usd,
            error=step.error,
            created_at=now,
            updated_at=now,
        )
        with self.transaction() as conn:
            seq = _next_seq(conn, step.run_id)
            record = StepRecord(
                id=record.id,
                run_id=record.run_id,
                seq=seq,
                kind=record.kind,
                name=record.name,
                status=record.status,
                input_json=record.input_json,
                output_json=record.output_json,
                idempotency_key=record.idempotency_key,
                attempt=record.attempt,
                max_attempts=record.max_attempts,
                latency_us=record.latency_us,
                tokens_in=record.tokens_in,
                tokens_out=record.tokens_out,
                cost_micro_usd=record.cost_micro_usd,
                error=record.error,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            conn.execute(
                """
                INSERT INTO steps (
                    id, run_id, seq, kind, name, status, input_json, output_json,
                    idempotency_key, attempt, max_attempts, latency_us, tokens_in,
                    tokens_out, cost_micro_usd, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _step_params(record),
            )
        return record

    def save_step(self, step: StepRecord) -> StepRecord:
        updated = StepRecord(
            id=step.id,
            run_id=step.run_id,
            seq=step.seq,
            kind=step.kind,
            name=step.name,
            status=step.status,
            input_json=step.input_json,
            output_json=step.output_json,
            idempotency_key=step.idempotency_key,
            attempt=step.attempt,
            max_attempts=step.max_attempts,
            latency_us=step.latency_us,
            tokens_in=step.tokens_in,
            tokens_out=step.tokens_out,
            cost_micro_usd=step.cost_micro_usd,
            error=step.error,
            created_at=step.created_at,
            updated_at=utc_now(),
        )
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE steps SET
                    status = ?, output_json = ?, attempt = ?, latency_us = ?,
                    tokens_in = ?, tokens_out = ?, cost_micro_usd = ?, error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    updated.output_json,
                    updated.attempt,
                    updated.latency_us,
                    updated.tokens_in,
                    updated.tokens_out,
                    updated.cost_micro_usd,
                    updated.error,
                    updated.updated_at,
                    updated.id,
                ),
            )
            if cursor.rowcount != 1:
                raise StoreError(f"step not found: {step.id}")
        return updated

    def get_step(self, step_id: str) -> StepRecord:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,)).fetchone()
        if row is None:
            raise StoreError(f"step not found: {step_id}")
        return _step_from_row(row)

    def list_steps(self, run_id: str) -> list[StepRecord]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY seq ASC",
                (run_id,),
            ).fetchall()
        return [_step_from_row(row) for row in rows]

    def get_effect(self, idempotency_key: str) -> dict[str, object] | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT output_json FROM effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        stored = row["output_json"]
        if not isinstance(stored, str):
            raise StoreError("effect row is corrupt")
        return as_dict(loads(stored))

    def refunded_cents(self, order_id: str) -> int:
        with self._read() as conn:
            row = conn.execute(
                "SELECT refunded_cents FROM refund_ledger WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        if row is None:
            return 0
        value = row["refunded_cents"]
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise StoreError("refund ledger is corrupt")

    def commit_effect(
        self,
        idempotency_key: str,
        tool_name: str,
        output: dict[str, object],
        order_id: str | None,
        amount_cents: int | None,
    ) -> dict[str, object]:
        """Record an external effect once.

        The ledger increment and the effect row share a transaction. A second
        call with the same key returns the original output and does not add
        the amount again. That is the crash-recovery path.
        """

        output_json = dumps(output)
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT output_json FROM effects WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                stored = existing["output_json"]
                if not isinstance(stored, str):
                    raise StoreError("effect row is corrupt")
                return as_dict(loads(stored))
            now = utc_now()
            conn.execute(
                """
                INSERT INTO effects (idempotency_key, tool_name, output_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (idempotency_key, tool_name, output_json, now),
            )
            if order_id is not None and amount_cents is not None:
                current = conn.execute(
                    "SELECT refunded_cents FROM refund_ledger WHERE order_id = ?",
                    (order_id,),
                ).fetchone()
                if current is None:
                    conn.execute(
                        """
                        INSERT INTO refund_ledger (order_id, refunded_cents, updated_at)
                        VALUES (?, ?, ?)
                        """,
                        (order_id, amount_cents, now),
                    )
                else:
                    already = current["refunded_cents"]
                    if not isinstance(already, int) or isinstance(already, bool):
                        raise StoreError("refund ledger is corrupt")
                    conn.execute(
                        """
                        UPDATE refund_ledger SET refunded_cents = ?, updated_at = ?
                        WHERE order_id = ?
                        """,
                        (already + amount_cents, now, order_id),
                    )
        return output

    def count_effects(self, tool_name: str) -> int:
        with self._read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM effects WHERE tool_name = ?",
                (tool_name,),
            ).fetchone()
        if row is None:
            return 0
        value = row["n"]
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise StoreError("effect count is corrupt")


def _next_seq(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS n FROM steps WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return 1
    value = row["n"]
    if isinstance(value, int) and not isinstance(value, bool):
        return value + 1
    raise StoreError("step sequence is corrupt")


def _step_params(step: StepRecord) -> tuple[object, ...]:
    return (
        step.id,
        step.run_id,
        step.seq,
        step.kind,
        step.name,
        step.status,
        step.input_json,
        step.output_json,
        step.idempotency_key,
        step.attempt,
        step.max_attempts,
        step.latency_us,
        step.tokens_in,
        step.tokens_out,
        step.cost_micro_usd,
        step.error,
        step.created_at,
        step.updated_at,
    )


def _text(row: sqlite3.Row, key: str) -> str:
    value = row[key]
    if isinstance(value, str):
        return value
    raise StoreError(f"column {key} is not text")


def _optional_text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise StoreError(f"column {key} is not text")


def _integer(row: sqlite3.Row, key: str) -> int:
    value = row[key]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise StoreError(f"column {key} is not an integer")


def _optional_integer(row: sqlite3.Row, key: str) -> int | None:
    value = row[key]
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise StoreError(f"column {key} is not an integer")


def _run_from_row(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=_text(row, "id"),
        status=require_run_status(_text(row, "status")),
        input_json=_text(row, "input_json"),
        output_json=_optional_text(row, "output_json"),
        budget_micro_usd=_integer(row, "budget_micro_usd"),
        spent_micro_usd=_integer(row, "spent_micro_usd"),
        consecutive_failures=_integer(row, "consecutive_failures"),
        created_at=_text(row, "created_at"),
        updated_at=_text(row, "updated_at"),
        error=_optional_text(row, "error"),
    )


def _step_from_row(row: sqlite3.Row) -> StepRecord:
    return StepRecord(
        id=_text(row, "id"),
        run_id=_text(row, "run_id"),
        seq=_integer(row, "seq"),
        kind=require_step_kind(_text(row, "kind")),
        name=_text(row, "name"),
        status=require_step_status(_text(row, "status")),
        input_json=_text(row, "input_json"),
        output_json=_optional_text(row, "output_json"),
        idempotency_key=_text(row, "idempotency_key"),
        attempt=_integer(row, "attempt"),
        max_attempts=_integer(row, "max_attempts"),
        latency_us=_optional_integer(row, "latency_us"),
        tokens_in=_integer(row, "tokens_in"),
        tokens_out=_integer(row, "tokens_out"),
        cost_micro_usd=_integer(row, "cost_micro_usd"),
        error=_optional_text(row, "error"),
        created_at=_text(row, "created_at"),
        updated_at=_text(row, "updated_at"),
    )
