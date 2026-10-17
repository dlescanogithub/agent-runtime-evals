# Changelog

## Unreleased

- Optional hosted providers, off unless `LIVE_MODE=1`: an OpenAI-compatible
  client for xAI and OpenAI, and a thin Anthropic Messages adapter. Key,
  base URL, model, and prices come only from the environment. No vendor
  price is shipped. `MAX_LIVE_SPEND_USD` caps each run and the process.
- A claimed `refund_completed` with no matching `send_refund` effect fails
  the run as `needs_review`.
- The six adversarial cases check invariants instead of the stub's tool list.
  A 2026-10-17 live run mostly ignored the injection, so those guards were
  barely exercised live.
- Reasoning tokens and provider cost ticks are counted. Cached input is
  priced from `LLM_CACHED_INPUT_USD_PER_MILLION` or logged as an upper bound.
- `make eval-live` writes cassettes outside `evals/cassettes` and fails
  closed without live config. CI still runs the stub only.
- The system prompt asks the model to call the gated tools. Tool schemas
  include descriptions. `edge_human_reject` rejects at the gate.
- Stub suite after these edits: 23/23, 38886 / 1902 tokens, 6937 micro-USD.
  Demo: 2408 / 124 tokens, 433 micro-USD. Live rerun numbers are not filled in.
- README section "Use cases, governance and business strategy": the Lumen
  Desk refund agent is the only implemented case. Ticket triage, scheduling,
  a personal-finance assistant, and a personal inbox assistant are design
  sketches. Governance points at the files that enforce it. ROI stays [EST]
  except the dated stub measurements.

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
