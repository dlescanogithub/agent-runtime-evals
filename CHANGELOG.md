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
- 22 synthetic eval cases and cassettes. The stub reads the customer
  message and obeys a few attacks; the tools block them. A deterministic
  checker (not an LLM judge) scores a checklist at threshold 0.80. A
  forced regression fails the gate. CI replays cassettes and does not
  notice a model change.
- Bearer token on the HTTP API (`API_TOKEN`), health check exempt.
  Approvals are idempotent. Two threads cannot execute one claimed step.
- CI: one install, pip cache, coverage in the job summary, gitleaks
  8.30.1 with a pinned checksum, Dependabot, and CODEOWNERS.
- Docs for the business case, discovery, scope, risks, metrics, cost,
  runbook, how to adapt this to a real customer, and a plain-language
  walkthrough.

Not in this version: Postgres `FOR UPDATE SKIP LOCKED`, OpenTelemetry, an
LLM judge, a human agreement study, the customer's identity provider, a
live model in CI, and a recorded demo GIF.
