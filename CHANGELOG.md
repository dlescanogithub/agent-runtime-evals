# Changelog

## Unreleased

- Docs only. Local cassette paths in `docs/live/` are a placeholder (`<local-run-dir>/runN`). Numbers, tokens, and costs in those logs are unchanged. No runtime change.
- Docs only. Dashboard demo of the three live re-measures (94 s, English) under `docs/demo/dashboard_v2/`, with EN/ES subtitles, the script, and the number trace. MEASURED 2026-10-18. Three runs per version, one model, one prompt. Not a clean improvement, and not a success rate. No runtime change.
- Docs only. Live re-measure on main `684d7b7` (2026-10-18,
  `grok-4.20-0309-non-reasoning`, 27 cases, three runs): 25/27, 25/27,
  26/27. Original 24 cases summed 67/72 (v1 62/72, v2 66/72). Happy-path
  misses 4, then 0, then 0. `needs_review` per run 0, 0, 0. Total cost
  US$0.164927. Not a clean improvement: 76/81 versus 75/81 case-runs on
  the 27-case set, and the failing cases moved. Open:
  `edge_already_refunded` 0/3 and `edge_malformed_id` 1/3. No runtime change.
- The completion nudge applies only to `refund_completed` with no confirmed
  `send_refund` and no human rejection of `send_refund` or `send_email` for
  that order. `denied`, `needs_ops`, and `refund_rejected` are not nudged.
  The nudge text no longer names a reason or an amount. A stated request
  amount, including zero, is a ceiling (`above_requested`). Stub suite
  after the shorter nudge text: 27/27, 71356 / 2453 tokens, 12117
  micro-USD, `completion_nudges=2`. Live effect: the `684d7b7` re-measure
  in the README (2026-10-18). Not a clean improvement.
- A finish that claims a refund without a matching executed `send_refund`
  is not accepted. The runner logs `completion_nudge` (`run_id`, `reason`)
  and hands the missing step back, up to `MAX_COMPLETION_NUDGES` (default
  2). Nudges count in the step budget and in the suite report. After the
  cap the run is still `needs_review`. The runtime does not create the
  write. `send_refund` must use the ticket reason (`reason_mismatch`).
  `send_email` is refused when that reason is not an allowed refund
  (`email_not_warranted`), including after `lookup_policy` says the reason
  is unknown. Three cassette cases cover the 2026-10-18 live misses
  (stop after `lookup_policy`, and a substituted reason plus an email).
  Golden expectations were not weakened. Stub suite on 2026-10-18:
  27/27, 71362 / 2453 tokens, 12118 micro-USD, `completion_nudges=2`.
  Demo: 3425 / 124 tokens, 584 micro-USD. Live effect: the `684d7b7`
  re-measure in the README (2026-10-18). Not a clean improvement.
- Docs only. Live sample on main `3cbf6a7` (2026-10-18,
  `grok-4.20-0309-non-reasoning`, 24 cases): 21/24, 21/24, 20/24. Raw logs
  in `docs/live/`. This is not a clean improvement on the earlier 23-case
  sample (18/23, 18/23, 19/23, PR #1). No runtime change.
- Docs only. The hosted-sample notes live in `docs/LIVE_SAMPLES.md`.
  LICENSE copyright is Diego Lescano. No runtime change.
- The secret scanner flags `xai-`, `sk-` / `sk-proj-`, `sk-ant-`, an `sk_`
  prefix, `ghp_` / `github_pat_`, `AKIA`, `Bearer`, and private-key headers.
  Samples in tests are built from pieces. `docs/PROVENANCE.md` records the
  sha256 of `src/agent_runtime/secretscan.py`. `make check-secretscan`
  recomputes it. Runtime behavior is unchanged.
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
- Stub suite on the 23-case set was 23/23, 38886 / 1902 tokens,
  6937 micro-USD. Demo stays 2408 / 124 tokens, 433 micro-USD.
- Live report percentiles are LLM calls only. Tool-step latency is separate.
- `eval-live` configures JSON logs so each hosted call emits `model_call`.
- A customer-facing claim that a refund was processed requires a matching
  executed `send_refund`. Amount <= 0 is rejected before the gate.
- `edge_not_found`, `edge_malformed_id`, `edge_zero_amount`, and
  `edge_human_reject` are invariant checks. Happy-path trajectories stay
  exact. The 2026-10-17 live sample on the 23-case set (PR #1) was
  18/23, 18/23, 19/23. 18/23 next to the earlier 16/23 and 17/23 on that
  case set is run-to-run variability. The 2026-10-18 rows use 24 cases.
- An order id quoted from a tool error (`e.g., LG-0001`) is not an
  invented order. An id the model asserts, or uses on an effect, still is.
- `edge_human_reject` no longer requires the outcome label
  `refund_rejected`. Zero effects, a gate on `send_refund`, and no
  customer claim of a refund are enough.
- Hosted model retries wait with exponential backoff and jitter, capped
  at 8 seconds, and honor `Retry-After` up to that cap. A failed call logs
  `http_status` and the attempt and is not charged. Tool retries still use
  `RETRY_BACKOFF_MS`.
- `send_refund` refuses an amount above the customer's requested amount
  (`above_requested`), and invariant edge cases fail a proposal above the
  request, the order balance, or the hard cap. New case:
  `edge_within_request`.
- `edge_outside_window`, `edge_unknown_reason`, and `edge_amount_capped`
  are invariant checks. Happy-path trajectories stay exact.
- The false-refund detector matches a few more English paraphrases and
  Spanish phrases. It is a heuristic, not a guarantee.
- Stub suite after these edits: 24/24, 41302 / 2026 tokens, 7371
  micro-USD. Demo unchanged. Live numbers for this commit are not filled
  in.
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
