# Metrics

Two columns. "In this repo" is what the code actually computes. "At a
customer" is what we would put on a review once a person is in the loop.
We do not fill the second column with numbers.

## Measured here

Run date 2026-10-18, version 0.1.0, model `stub-llm-v1`. Suite figures are
from `make eval` (cassette replay). The demo cost is from `make demo`.
Both use the synthetic price in `pricing.py`, not a vendor invoice.

| Metric | How | Result |
|---|---|---|
| Golden-set pass rate | `make eval`, deterministic checks and the code checker | 27/27, stub |
| Checker mean | Fraction of six checklist items, scored in code. Not an LLM judge. | 1.00 (threshold 0.80) |
| Completion nudges | Steps of kind `nudge` in the cassette suite | 2 |
| Regressions the gate can see | `make eval-regression` | The bad trajectory fails the process. This shows the mechanism. It is not a count of production incidents. |
| Cost per demo run | Sum of per-step stub costs, including crash and resume | 584 micro-USD |
| Cost of the suite | Same, 27 stub cases | 12118 micro-USD |
| Step latency | Microseconds inside this process. Not an SLO. | LLM-call p50 1 µs on 2026-10-18, `make eval`, v0.1.0. Tool-step p50 and p95 are separate fields in `evals/results/latest.json` and are not checked by tests. |
| Ungated external effects in the suite | Effect rows versus observed gates | 0 ungated. The cases require the gate. |

Tokens and cost are deterministic for the stub and are checked by tests
against the README. Latency fields in `evals/results/latest.json` are not
part of that check, so `make eval` can rewrite them without breaking pytest.

## Defined for a customer, not measured here

| Metric | Definition | Why it is empty |
|---|---|---|
| Approved without edit | Share of gated actions the reviewer approves with the amount, reason, and recipient unchanged | No human panel in this repo |
| Policy violations that reach the reviewer | Drafts that ask for an amount the tool would later refuse | Would be counted from the queue during the shadow period |
| Queue age | Time a step spends in `waiting_review` | No production traffic |
| Cost per completed run | Model spend plus reviewer minutes | Reviewer minutes are [EST] only. See the business case. |
| Failed runs | `failed` status, split by `budget_exceeded`, `circuit_open`, `provider_error` | The suite expects completed cases. Failures are unit-tested, not a rate. |
| LLM-judge agreement with a human | Agreement on a labeled sample | Not started. The CI checker is code. Do not invent a kappa. |

## How "good" is decided in CI

A case fails if any deterministic check fails: tool trajectory, final
schema, outcome, amount, effect counts, or a missing gate.

A case also fails if the checker score is under `EVAL_CHECK_THRESHOLD`
(default 0.80), even when the deterministic checks pass. With six checks,
one miss scores about 0.83 and still passes. Two misses score about 0.67
and block. The forced regression fails both levels.

The threshold is a config value so a customer can tighten it. Lowering it
to hide a failure is a process violation, not a feature.
