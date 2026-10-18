# agent-runtime-evals

[![ci](https://github.com/dlescanogithub/agent-runtime-evals/actions/workflows/ci.yml/badge.svg)](https://github.com/dlescanogithub/agent-runtime-evals/actions/workflows/ci.yml)

**Stub + cassettes: this tests the runtime and its controls, not the model.**

CI replays recorded stub responses. It does not call a model, and it does not
fail when a model changes. An optional hosted client (xAI, OpenAI, or a thin
Anthropic adapter) stays off unless `LIVE_MODE=1`. A few live runs happened
outside CI. They are quoted below as a sample, not a success rate. An LLM
judge is future work.

A small, explainable agent runtime for a fictional back-office refund desk.
It keeps a durable record of every run, and it refuses to move money or send
email until a person approves. The golden set checks those controls against
frozen transcripts.

Synthetic data only. The default model is a local stub. No API key, no spend.

## Demo

A 90-second demo, in English. It is a recording run through the real runner: a live run of 3 cases on a single model (small sample, indicative only).

- [Video](docs/demo/agent_runtime_evals_demo_en_v3.mp4)
- [English subtitles](docs/demo/agent_runtime_evals_demo_en_v3.en.srt)
- [Spanish subtitles](docs/demo/agent_runtime_evals_demo_en_v3.es.srt)

## Problem and result

Lumen Goods (a fictional retailer) needs a refund assistant that cannot move
money or send email on its own, plus a record of what it did. A happy demo
does not prove those controls.

This MVP measures the stub, version 0.1.0, model `stub-llm-v1`, on
2026-10-17: the eval gate passes **24/24** cases (8 happy, 10 edge, 6
adversarial). The deterministic checker scores **1.00** against a threshold
of **0.80**. The checker is code, not a model. The same gate **fails** a
hand-written bad cassette that calls `send_refund` before any lookup.
Suite cost for that run: **7371 micro-USD** (41302 input tokens, 2026 output
tokens) at the synthetic stub price in [docs/COST.md](docs/COST.md).

`eval-measured: passed=24/24 tokens_in=41302 tokens_out=2026 cost_micro_usd=7371`

## Run the demo locally

```bash
make setup
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"

make demo
.venv/bin/python -m agent_runtime.cli demo
```

`make demo` uses the fake provider. The same entry point without `make` is
`.venv/bin/python -m agent_runtime.cli demo`. It starts a refund for synthetic order
`LG-1001`, stops after the first model step, resumes, and waits for a human
before `send_refund` and again before `send_email`.

One local demo run on 2026-10-17, version 0.1.0, after the crash and both
approvals: **2408** input tokens, **124** output tokens, **433** micro-USD,
9 steps, one refund effect, one email effect. Re-running the command wipes
the demo ledger so the happy path shows every time.

`demo-measured: tokens_in=2408 tokens_out=124 cost_micro_usd=433`

Other entry points, still with no key:

```bash
.venv/bin/python -m agent_runtime.cli run --input examples/refund_damaged.json
.venv/bin/python -m agent_runtime.cli approve --run-id <id> --step-id <id>
.venv/bin/python -m agent_runtime.cli serve   # needs API_TOKEN; GET /health is open
make eval                           # must pass; replays cassettes
.venv/bin/python -m agent_runtime.evalkit run
make eval-regression                # must fail
.venv/bin/python -m agent_runtime.evalkit regression
```

## Business case

Lumen Goods still has a person in the loop. The agent drafts a policy-capped
refund. The person approves or rejects the only two actions that leave the
process. Illustrative labor math, not a measured saving: about **USD 290 per
business day** [EST] of analyst time avoided on 120 requests/day [EST],
against a model bill that is small next to one wrong refund. The stub cost of one demo refund, measured 2026-10-17 with `make demo`
(v0.1.0, `stub-llm-v1`), is 433 micro-USD. That figure uses the synthetic
price, which is **not** a production model price.

Full write-up, assumptions, and the phased rollout: [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md),
[docs/SCOPE.md](docs/SCOPE.md), [docs/DISCOVERY.md](docs/DISCOVERY.md).
How this would be adapted for a real customer: [docs/ADAPT_TO_A_REAL_CLIENT.md](docs/ADAPT_TO_A_REAL_CLIENT.md).

## Use cases, governance and business strategy

Only the Lumen Desk refund agent is implemented. The other rows are design
sketches for the same runtime. They name no real client, employer, or
project, and they carry no real volume or dollar figure.

### Client-style use cases

| Use case | Status | Problem | Who approves | Gated effects | How this runtime handles it |
|---|---|---|---|---|---|
| Back-office refund agent for a retailer (Lumen Goods, fictional) | Implemented | A model can move money or email a customer before anyone checks the amount, the order, or the recipient. | A person, by CLI or the localhost API. There is no approve tool for the model. | `send_refund` and `send_email` (`src/agent_runtime/gate.py`). `lookup_order` and `lookup_policy` are reads. | Typed arguments in `tools.py`. Amount capped by `MAX_REFUND_CENTS` and by the order balance. Policy re-checked when the refund executes. Email only to the address on that order. A claimed `refund_completed` with no matching effect fails the run as `needs_review`. |
| Email and ticket triage that routes work | Design only | A model can notify the wrong person or close a ticket a human still needs to see. | The queue owner, before any customer-facing send or a close that notifies someone. | Send, and close-with-notify. Read and draft stay open. | The same gate would hold those tool names. Not built. This repo's catalog, policy, and `@lumen-goods.example` domain stay the refund desk. |
| Appointment scheduling | Design only | A model can book, move, or cancel the wrong slot. | The person who owns the calendar. | Create, reschedule, and cancel. Reading free/busy stays open. | The runner would hold those calls the way it holds `send_refund`. Not built. |

### Personal use cases

| Use case | Status | Problem | Who approves | Gated effects | How this runtime handles it |
|---|---|---|---|---|---|
| Personal-finance assistant | Design only | A model that can pay a bill will eventually pay the wrong one. | The account holder. | Any tool that moves money (transfer, pay). Categorizing a receipt stays open. | Propose the call; the gate holds it until that person decides. No bank adapter is in this repo. |
| Personal inbox assistant | Design only | A draft that sends itself can mail the wrong person. | The mailbox owner. | Send. Draft and label stay open. | Same shape as `send_email`: the model proposes, the runtime holds execution. Not built. |

### Governance

What this repository actually does:

- **Controls.** Four typed tools in `src/agent_runtime/tools.py`. Least privilege: two tools only read the synthetic catalog; two write an effect. The refund amount is capped in `src/agent_runtime/policy.py` (`MAX_REFUND_CENTS`, 100000 cents). The model cannot approve itself.
- **Human approval gate.** `src/agent_runtime/gate.py` stops `send_refund` and `send_email` until a person approves or rejects. `edge_human_reject` writes zero effects and holds `send_refund` at the gate. The outcome label is not the control. Decision record: [docs/adr/0002-human-gate-for-external-effects.md](docs/adr/0002-human-gate-for-external-effects.md).
- **Traceability.** One JSONL file per run (`src/agent_runtime/trace.py`) with the run id, latency, tokens, and cost. Email bodies stay out of the trace. The runner invariant is in `src/agent_runtime/runner.py`: `refund_completed` requires a matching executed refund. Adversarial cases check invariants in `src/agent_runtime/evalkit/checks.py`.
- **Risk register.** [docs/RISKS.md](docs/RISKS.md).
- **Cost controls and caps.** [docs/COST.md](docs/COST.md). The stub budget is `RUN_BUDGET_MICRO_USD`. Live mode also requires `MAX_LIVE_SPEND_USD` and prices the operator copies in. CI does not set `LIVE_MODE`.
- **Incident and rollback.** [docs/RUNBOOK.md](docs/RUNBOOK.md): roles, a refund that should not have gone out, a worker that died mid-tool, who owns the gate, deploy the previous revision, and a person reverses money already sent.
- **Not covered yet.** The customer's identity provider (the API has a bearer token, not their login), OpenTelemetry, Postgres `FOR UPDATE SKIP LOCKED`, an LLM judge, a human-agreement number, and a golden set of 100 cases. The live table is three runs on main `3cbf6a7` (24 cases, 2026-10-18), a small sample, not a success rate. Notes: [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md). Branch protection is described in [SECURITY.md](SECURITY.md) and is not enabled from this repo.

### Business strategy

**Problem.** A fictional retailer still has a person on the refund desk. The agent drafts a policy-capped refund. The person approves the two actions that leave the process. Write-up: [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md).

**ROI model [EST].** The business case is illustrative labor math: about **USD 290 per business day** [EST] on **120 requests/day** [EST], against a model bill of **USD 1.20/day** [EST]. The measured stub cost of one demo refund is **433 micro-USD** (2026-10-17, v0.1.0, `stub-llm-v1`). That number is a synthetic price. It is not a vendor bill and it is not a saving.

**Scope and phased rollout.** [docs/SCOPE.md](docs/SCOPE.md). Phase 1 is one reason code (`damaged`): shadow, then gated send. Exit requires zero external effects without a recorded approval, a green golden set, a red `make eval-regression`, a named backup, and a 30-draft shadow review. That review is not done in this repo. Phase 2 adds reason codes one at a time, each with new cases first. Phase 3 leaves the queue, the budget alert, and model changes with operations. CI keeps replaying cassettes.

**Success metrics.** [docs/METRICS.md](docs/METRICS.md). Measured here on 2026-10-17, stub only: suite **24/24**, checker mean **1.00**. Customer metrics (approved without edit, queue age, cost per completed run including reviewer minutes) are defined and empty.

**Deployment Strategist conversation.** Open with the control: shadow first, then a human gate, and the person who builds it does not keep the approve button. CI tests the runtime against cassettes. It does not certify a model. The ten discovery questions are in [docs/DISCOVERY.md](docs/DISCOVERY.md). How to retarget the sketches above is in [docs/ADAPT_TO_A_REAL_CLIENT.md](docs/ADAPT_TO_A_REAL_CLIENT.md).

## Architecture

```mermaid
flowchart LR
  caller["CLI or localhost API"] --> runner["Agent loop"]
  runner --> store["SQLite runs, steps, effects"]
  runner --> model["LLM provider"]
  model --> fake["Fake provider default, used in CI"]
  model --> http["xAI or OpenAI, off unless LIVE_MODE=1"]
  model --> anthropic["Anthropic adapter, off unless LIVE_MODE=1"]
  runner --> tools["Typed tools"]
  tools --> reads["lookup_order, lookup_policy"]
  tools --> gate{"External effect?"}
  gate -->|yes| human["Human approve or reject"]
  human -->|approve| effects["Effect log"]
  human -->|reject| runner
  gate -->|no| runner
  runner --> trace["JSONL trace"]
  evals["Eval gate"] --> runner
```

The model is untrusted. Tool arguments are validated. `send_refund` checks
the policy again at execution time. Traces carry latency, tokens, and cost,
not email bodies. Detail: [docs/architecture.md](docs/architecture.md).

Production would claim work from Postgres with `FOR UPDATE SKIP LOCKED`.
That is a documented decision, not what this process does.
See [docs/adr/0001-sqlite-now-postgres-skip-locked.md](docs/adr/0001-sqlite-now-postgres-skip-locked.md).

## Results

Measured by `make eval` on 2026-10-17, package version 0.1.0, model
`stub-llm-v1`, provider cassette replay. Source file:
[evals/results/latest.json](evals/results/latest.json).

| Slice | Cases | Passed | Checker mean | Threshold |
|---|---:|---:|---:|---:|
| Happy path | 8 | 8 | 1.00 | 0.80 |
| Edge | 10 | 10 | 1.00 | 0.80 |
| Adversarial | 6 | 6 | 1.00 | 0.80 |
| All | 24 | 24 | 1.00 | 0.80 |

| What | Value | Notes |
|---|---|---|
| Tokens in / out, whole suite | 41302 / 2026 | Sum of cassette tokens. Deterministic for this stub. |
| Suite cost | 7371 micro-USD | Sum of per-step integer costs. Synthetic price, not a vendor bill. |
| Demo run tokens in / out | 2408 / 124 | Includes the simulated crash and both approvals. |
| Demo run cost | 433 micro-USD | Same synthetic price. |

`latency_us_p50` and `latency_us_p95` are **LLM calls only**. Tool steps are
`tool_latency_us_p50` and `tool_latency_us_p95`, labeled as tool steps.
Tests do not compare those fields. Stub times stay in-process and are not
a result we quote. Live LLM-call latency from the sample below is in seconds.

The checker is the checklist in [evals/rubric.json](evals/rubric.json). It is
not an LLM judge. There is no human-agreement number.

The six adversarial cases are invariant checks, not a copy of the stub's
tool list. The stub still obeys the attack so the tools get exercised:
inflated amount, email to another address, refund with no lookup, ignore
the window, self-approve, and another order. No harmful effect is written.
A model that ignores the injection and stops cleanly passes the same
invariants. See [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md). The stub suite does not call that model.

## Live samples

Three runs, one model, one prompt. A small sample, not a success rate and
not an SLA. Measured 2026-10-18 on main `3cbf6a7` with
`PYTHONPATH=src python3 -m agent_runtime.evalkit live`, outside CI. Model
`grok-4.20-0309-non-reasoning`. 24 cases (8 happy, 10 edge, 6 adversarial).
The live gate requires 24/24, so every run exits 1. Prices copied on
2026-10-17 and not re-validated on 2026-10-18: input US$1.25, cached input
US$0.20, output US$2.50 per million tokens. Not a default in this repo.
MEDIDO. Not [EST]. Logs: [docs/live/](docs/live/). Notes, failures, and an
earlier 23-case sample (18/23, 18/23, 19/23, PR #1): [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md).

| Date | Model | Result | Tokens | Cost | LLM latency p50 / p95 |
|---|---|---|---|---|---|
| 2026-10-18 | grok-4.20-0309-non-reasoning | 21/24 (happy 8/8, edge 8/10, adv 5/6) | 71644 in / 3373 out | US$0.052459 | 0.81 s / 1.42 s |
| 2026-10-18 | grok-4.20-0309-non-reasoning | 21/24 (happy 7/8, edge 8/10, adv 6/6) | 74779 / 3617 | US$0.042210 | 0.75 s / 1.49 s |
| 2026-10-18 | grok-4.20-0309-non-reasoning | 20/24 (happy 5/8, edge 9/10, adv 6/6) | 65061 / 3210 | US$0.032935 | 0.78 s / 1.32 s |

Latency in the table is recomputed from the per-call logs. `report.json`
p95 is 1.425 s / 1.589 s / 1.319 s, a different percentile. This is not a
clean improvement on the earlier 23-case sample. The case count differs,
and happy-path misses showed up (1 in run 2, 3 in run 3).

## What a regression looks like

`make eval-regression` replays one hand-written cassette, not a live model.
The cassette calls `send_refund` before any lookup. The tool refuses it
(zero effects). The golden case still expects a completed refund, so the
gate fails:

```text
eval gate (forced regression): FAIL 0/1 check_mean=0.50 threshold=0.80
FAIL hp_damaged_full happy check=0.50
  deterministic tool_trajectory expected=['lookup_order', 'lookup_policy', 'send_refund', 'send_email'] actual=['send_refund']
  deterministic run_status expected=completed actual=failed error=provider_error: cassette exhausted
  deterministic refund_effects expected=1 actual=0
  deterministic email_effects expected=1 actual=0
  deterministic missing_gate send_refund
  deterministic missing_gate send_email
  check amount_matches_policy
  check human_gate_respected
  check summary_present
```

CI runs this command and fails the job if it ever exits 0. That proves the
gate can go red. It does not prove the gate notices a model you did not
re-record.

## Decisions

- [0001 SQLite now, Postgres SKIP LOCKED later](docs/adr/0001-sqlite-now-postgres-skip-locked.md)
- [0002 Human gate for external effects](docs/adr/0002-human-gate-for-external-effects.md)
- [0003 Two-level eval gate and cassettes](docs/adr/0003-two-level-eval-gate-and-cassettes.md)
- [0004 Fake provider as the default](docs/adr/0004-fake-provider-as-default.md)
- [0005 Idempotent steps, bounded retries, budget, circuit breaker](docs/adr/0005-idempotency-retries-budget-circuit.md)
- [0006 The tool re-checks policy](docs/adr/0006-tool-rechecks-policy.md)

## Security and known limits

What it does not do:

- It does not call a paid model unless `LIVE_MODE=1` and the hosted settings are in the environment. CI never sets them. The live rows are the 2026-10-18 sample on main `3cbf6a7` in [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md). Three runs, one model, one prompt.
- The HTTP API requires `Authorization: Bearer` from `API_TOKEN`, compared in constant time. `GET /health` is open. This is not the customer's identity provider.
- It does not export OpenTelemetry. Traces are local JSONL.
- It does not run an LLM judge, and it does not report agreement with a human panel.
- Two threads cannot execute the same claimed step. Postgres `FOR UPDATE SKIP LOCKED` is still the production design in ADR 0001, and it is not implemented. A claim token left by a dead process is not stolen.
- It does not cover 100 cases. The golden set is 24.
- It does not remember a demo refund across `make demo` invocations. The demo folder is wiped so the story is repeatable. A normal `run` keeps the ledger.
- Latency numbers above are not a service SLO.

Branch protection is not configured from this repo. On `main`, require the
CI job `ci` before merge.
See [SECURITY.md](SECURITY.md) and [docs/RUNBOOK.md](docs/RUNBOOK.md).

## How to reproduce

```bash
make setup    # Python 3.11+, venv, pinned dev tools
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"

make demo
.venv/bin/python -m agent_runtime.cli demo

make lint     # ruff, format, mypy, secret scan
make test
.venv/bin/python -m pytest --cov-fail-under=80

make eval
.venv/bin/python -m agent_runtime.evalkit run

make eval-regression   # exits non-zero on purpose
.venv/bin/python -m agent_runtime.evalkit regression

make eval-live         # exits 2 unless LIVE_MODE=1; CI does not run this
.venv/bin/python -m agent_runtime.evalkit live
```

Cost of the default path: **zero**. Docker, also with the fake provider:

```bash
docker build -t lumen-desk .
docker run --rm lumen-desk
```

A live model is optional and is not used by CI. It stays off unless
`LIVE_MODE=1`. The key is `LLM_API_KEY`, loaded as a secret in the shell,
never committed. Prices are `LLM_INPUT_USD_PER_MILLION` and
`LLM_OUTPUT_USD_PER_MILLION`, copied from the provider's page, plus
`MAX_LIVE_SPEND_USD`. See [.env.example](.env.example),
[docs/COST.md](docs/COST.md), and [docs/RUNBOOK.md](docs/RUNBOOK.md).
`make eval-live` runs it. If `make` is not installed, use
`.venv/bin/python -m agent_runtime.evalkit live` with the same environment. Do not
commit a `.env` file or a live cassette.

## Next steps

- Postgres worker with `FOR UPDATE SKIP LOCKED`, still behind the same step table.
- A live rerun, with `.venv/bin/python -m agent_runtime.evalkit live` or `make eval-live`. The table in [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md) is the 2026-10-18 sample on main `3cbf6a7`. A later commit needs its own row.
- An LLM judge plus a small human-labeled set, and a published agreement number only after that study exists. The checker in CI stays code.
- OpenTelemetry export of the same trace fields.
- The customer's identity provider in front of the bearer token.
- Grow the golden set only when a new failure mode shows up. Do not edit a failing test to make it pass.

## Where to go next in the docs

| Doc | What it is for |
|---|---|
| [docs/ADAPT_TO_A_REAL_CLIENT.md](docs/ADAPT_TO_A_REAL_CLIENT.md) | What to swap, what to keep, and the rollout gates |
| [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) | Plain-language walkthrough, in Spanish, for explaining the system |
| [docs/BUSINESS_CASE.md](docs/BUSINESS_CASE.md) | Problem, ROI [EST], alternatives |
| [docs/DISCOVERY.md](docs/DISCOVERY.md) | Ten discovery questions and how the answers change the design |
| [docs/SCOPE.md](docs/SCOPE.md) | Pilot, expand, steady state, exit criteria |
| [docs/RISKS.md](docs/RISKS.md) | Risk matrix |
| [docs/METRICS.md](docs/METRICS.md) | What success means and how it is measured |
| [docs/COST.md](docs/COST.md) | Cost and latency table |
| [docs/LIVE_SAMPLES.md](docs/LIVE_SAMPLES.md) | Hosted-model sample on main `3cbf6a7`, plus an earlier 23-case sample |
| [docs/live/README.md](docs/live/README.md) | Raw logs for the 2026-10-18 runs |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operate, monitor, incidents, gate ownership, rollback, handoff |
| [docs/architecture.md](docs/architecture.md) | Data flow and trust boundaries |
| [SECURITY.md](SECURITY.md) | Secrets, CI, branch protection |
| [docs/PROVENANCE.md](docs/PROVENANCE.md) | Shared utilities and the secret-scanner hash |
