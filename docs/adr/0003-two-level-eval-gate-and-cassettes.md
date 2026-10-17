# ADR 0003 — Two-level eval gate, cassettes in CI

## Status

Accepted.

## Context

A refund agent fails in two different ways.

- The trajectory is wrong: it skips a lookup, calls a tool it should not,
  or returns a shape the caller cannot read. That is a deterministic fact.
- The draft is sloppy in a way a checklist can score: amount, gate, leakage,
  a summary that repeats the injection. A later version of that checklist
  might be a model. This one is code.

Live model calls in CI cost money and do not repeat. A red build that is
red only sometimes does not get trusted.

## Options

1. One live call per pull request. Rejected. Cost and flake.
2. Only the trajectory checks. Rejected. We also want a checklist with a
   threshold. That checklist is code. An LLM judge is future work, not this
   ADR.
3. Cassettes plus two levels. Chosen.

## Decision

- `evals/cases.json` holds the expected trajectory, outcome, amount, gates,
  and effect counts. Those checks always fail the process.
- `evals/cassettes/` holds the stub's completions. CI replays them. The
  tools, the gate, and the ledger still run.
- `evals/rubric.json` is the checklist. `score_checks` scores it in process.
  It does not call a model. The case fails if the score is under 0.80.
- `evals/regressions/skip_lookup.json` is a bad transcript. `make
  eval-regression` must exit non-zero. CI fails if that command exits 0.
- Re-recording cassettes is a command (`python -m agent_runtime.evalkit
  record`) and a reviewed diff. It is not something CI does.

## Consequences

- CI spend on this repo is zero.
- CI does not notice a model change. It only replays what was recorded.
  A future live run would be a separate, capped job. Re-recording would be
  a reviewed diff. This repository does not run that job.
- We do not publish agreement with a human panel. There is no LLM judge.
  Adding one later does not remove the deterministic checks.
- The threshold is intentionally not 1.0. One missed rubric check on a
  six-check list scores about 0.83 and passes. Two miss and the build
  fails. Tightening it is a config change with a reason, not a silent edit.
