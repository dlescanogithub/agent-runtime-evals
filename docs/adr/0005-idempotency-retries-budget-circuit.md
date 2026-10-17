# ADR 0005 — Idempotent steps, bounded retries, budget, circuit breaker

## Status

Accepted.

## Context

The loop will crash, the catalog (or a real order system) will time out,
and a model will sometimes call a broken tool in a circle. "Retry forever"
and "retry a rejected refund" are different mistakes.

## Options

1. At-most-once: never retry. Rejected. A timeout during a read would fail
   a run that could have succeeded.
2. Unbounded retry. Rejected. A 500 that lasts an hour becomes a bill and
   a pile of duplicate attempts.
3. Bounded retries for transient errors, no retry for business denials,
   an effect key for anything that leaves the process, a budget, and a
   circuit breaker. Chosen.

## Decision

- Transient errors (timeouts, HTTP 429 and 5xx) retry up to
  `MAX_STEP_ATTEMPTS`. The attempt counter is saved before the call, so a
  crash does not reset the budget of attempts.
- Validation errors, policy denials, and human rejections are normal tool
  results. They are not retried by the runner.
- The effect key is `tool + canonical business arguments`. The model does
  not get to pick it. The effect insert and the ledger update share a
  transaction. A second call returns the original receipt and does not add
  the amount again. The lookup happens before the policy re-check, because
  the balance has already changed.
- `RUN_BUDGET_MICRO_USD` is model spend, not the refund amount. After a
  call crosses it, the run fails before the next side effect.
- `CIRCUIT_BREAKER_THRESHOLD` counts consecutive tool failures. A successful
  model turn does not clear it. Otherwise a model that keeps calling a dead
  tool would reset the breaker every time.

## Consequences

- A failed test that shows a double charge is a product bug, not a reason
  to loosen the test.
- Backoff defaults to 0 ms so CI is fast. A live provider should set
  `RETRY_BACKOFF_MS`.
- The happy path's idempotency is covered by unit tests, including a crash
  after the effect row and before the step is marked succeeded.
