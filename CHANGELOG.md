# Changelog

## 0.1.0 — 2026-10-17

First MVP of the Lumen Desk runtime.

- Agent loop with a typed tool list, a fake provider by default, and an
  optional OpenAI-shaped HTTP client.
- SQLite ledger for runs, steps, effects, and refund totals. Resume after
  an interrupt. Idempotent external effects. Bounded retries, a per-run
  model budget, and a circuit breaker.
- Human gate for `send_refund` and `send_email`, via CLI and a localhost API.
- JSONL traces with latency, tokens, and cost.
- 22 synthetic eval cases, cassettes, a rubric judge with threshold 0.80,
  and a forced regression that fails the gate.
- CI jobs for ruff, mypy, pytest, the eval gate, and secret scanning.
- Docs for the business case, discovery, scope, risks, metrics, cost,
  runbook, and a plain-language walkthrough.

Not in this version: Postgres `FOR UPDATE SKIP LOCKED`, OpenTelemetry, an
LLM judge, a human agreement study, API authentication, a live model in CI.
