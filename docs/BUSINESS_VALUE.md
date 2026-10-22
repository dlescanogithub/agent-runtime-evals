# Value realization plan: adopting `agent-runtime-evals`

> **Important notice**
>
> - **Fictional buyer.** Lumen Goods is the fictional home-goods retailer
>   already used in this repository. It is not a real customer and not an
>   employer. This plan does not add a second company.
> - **Inspired by a value-realization plan:** a buyer, levers, KPIs with a
>   baseline and a target, a cost table, and a measurement plan. It is not
>   an official AWS template, and it does not claim the AWS Business Value
>   Realization competency. That competency is awarded to partner companies,
>   not to individuals.
> - **Labels used in this file, and only these:**
>   - **MEASURED**: a figure this repository recorded from a run, with the
>     date and version the repo gives.
>   - **[EST]**: an illustrative estimate. Repo estimates stay estimates.
>     Arithmetic on them is still [EST].
>   - **[SYN]**: not used below. A second volume, a day-count, or a build
>     budget is not invented here.
>   - **SIMULATED**: the demo's scripted crash and resume. Not a live outage.
>   - **UNVERIFIED**: the repo names it and does not record a number, or
>     this plan refuses to fill the gap.
> - Repository: https://github.com/dlescanogithub/agent-runtime-evals.
>   Package **0.1.0**. Stub suite and demo figures below are the 2026-10-18
>   rows in the README and in [evals/results/latest.json](../evals/results/latest.json).
>   The pytest line was re-run locally on 2026-10-22. Python sources for
>   that run match main `7ea9d66`. This document does not change them.

---

## 1. Problem and buyer

Refund requests at the fictional retailer are repetitive: read the order,
read the policy, pick an amount, write to the customer. A happy demo does
not show the failure that matters. A prompt edit or a model swap can refund
the wrong amount, skip the policy, or email the wrong person, and the first
signal is a complaint. That problem statement is the one in
[BUSINESS_CASE.md](BUSINESS_CASE.md). The dollars attached to it there are
[EST], not a measured loss.

**Buyer.** The refund desk of Lumen Goods, fictional. Roles, from
[RUNBOOK.md](RUNBOOK.md):

| Role | Owns | Does not own |
|---|---|---|
| Operator | The process, the queue, restart, rollback | Approving a refund |
| Approver, with a named backup | `send_refund` and `send_email` | Merging the prompt that produced them |
| Change owner | The pull request for a prompt, a policy rule, or a cassette | Approving that merge, or the refunds that follow it |

The builder does not keep the approve button
([SCOPE.md](SCOPE.md), "After handoff"). A job title for an executive
sponsor is **UNVERIFIED**. The runbook names roles, not a person and not a
department beyond the desk.

The pilot does not remove the analyst. The agent may read one order, read
the policy for one reason, and propose `send_refund` and `send_email`. A
person still approves both. That split is [BUSINESS_CASE.md](BUSINESS_CASE.md).

## 2. Value levers

| Lever | What changes | What this repo can say |
|---|---|---|
| Read-and-draft time | The person reviews a draft instead of assembling it | [EST]. 6 minutes today, 45 seconds of review. Not timed here. |
| Wrong amount or wrong order | `send_refund` re-checks policy, caps the amount, and waits for a person | The control is in code (`policy.py`, `tools.py`, `gate.py`). The dollar size of a prevented error is [EST]. |
| Wrong recipient | Email only to the address on that order, and only after approval | Same. A count of bad emails stopped in a real mailbox is UNVERIFIED. |
| Double pay on retry or crash | The effect key is the business action. A retry of a recorded effect is a no-op | Mechanism tested. A production double-pay count is UNVERIFIED. |
| A bad trajectory in CI | `make eval-regression` replays a cassette that calls `send_refund` before lookup. The gate fails | MEASURED as a mechanism. It is not a count of incidents, and it does not notice a model you did not re-record. |
| Spend | `RUN_BUDGET_MICRO_USD` defaults to 100000 (USD 0.10). Live mode also needs `MAX_LIVE_SPEND_USD` | The caps are configuration. A vendor invoice is not in this repo. |

Fully automatic refunds lost the comparison in
[BUSINESS_CASE.md](BUSINESS_CASE.md): the error cost is treated as larger
than the time saved. That comparison is [EST].

## 3. Baseline versus target KPIs

| KPI | Baseline | Target | How it would be measured | Stage |
|---|---|---|---|---|
| Golden-set pass, stub | 27/27 MEASURED 2026-10-18, v0.1.0, `stub-llm-v1` (10 happy, 11 edge, 6 adversarial) | 27/27 on cassette replay. A larger customer set is not in this repo | `make eval` | Now, in CI |
| Checker mean | 1.00 against 0.80 MEASURED the same run. The checker is code, not a model | Stay at or above 0.80. Do not lower the threshold to hide a miss | [evals/rubric.json](../evals/rubric.json) | Now, in CI |
| Forced regression | The bad cassette fails the process MEASURED (README, "What a regression looks like") | The command keeps exiting non-zero. CI fails the job if it exits 0 | `make eval-regression` | Now, in CI |
| Ungated external effects in the stub suite | 0 MEASURED ([METRICS.md](METRICS.md)) | 0 | Effect rows versus gates | Now |
| External effects without a recorded approval | Not observed in the suite. A real queue has not run | 0, checked from the ledger. Phase 1 exit in [SCOPE.md](SCOPE.md) | Ledger | Phase 1. The 30-draft shadow review is not done. UNVERIFIED |
| Analyst minutes per request | 6 minutes [EST] | 45 seconds of review [EST] | A timed sample. Empty here | Phase 1 shadow |
| Volume | 120 requests per business day [EST] | The [EST] is the planning input, not a target to beat | Not counted here | Discovery |
| Approved without edit | No human panel. Defined and empty in [METRICS.md](METRICS.md) | No numeric target in this repo | Queue sample | UNVERIFIED |
| Queue age | No production traffic. The runbook does not set a limit | A limit the customer chooses. UNVERIFIED | Time in `waiting_review` | UNVERIFIED |
| Cost of one demo refund | 584 micro-USD MEASURED 2026-10-18, including a SIMULATED crash and both approvals. An earlier `make demo` on 2026-10-17 was 433 micro-USD | Under a cap the customer sets. That cap is UNVERIFIED. The code cap is `RUN_BUDGET_MICRO_USD` | `make demo` | Now, synthetic price only |
| Suite cost, 27 stub cases | 12117 micro-USD MEASURED 2026-10-18 (71356 in, 2453 out, 2 completion nudges) | Not a savings target. It is the cassette bill at the synthetic price | `make eval` | Now |
| Live pass count | On main `684d7b7`, 2026-10-18, model `grok-4.20-0309-non-reasoning`: 25/27, 25/27, 26/27 MEASURED. The live gate wants 27/27, so each run exits 1 | Do not promote this sample to a target rate | `python -m agent_runtime.evalkit live`, outside CI | Sample only |
| Pytest line coverage | 110 passed on four local runs MEASURED 2026-10-22, Python 3.12.3. Line coverage printed 88.05% twice and 87.82% twice. See the README Proof section | CI fail-under is 80%, which both totals clear | The CI `pytest --cov` step | Now |
| Model bill per business day | USD 1.20 [EST] at USD 0.01 per run [EST] | Not a measured budget | A vendor invoice, which this repo does not have | UNVERIFIED as a bill |

The stub price is $0.15 / 1M input tokens and $0.60 / 1M output tokens
([COST.md](COST.md)). It is not a vendor page. Live prices used on
2026-10-18 were copied on 2026-10-17 and not re-checked that day: input
US$1.25, cached input US$0.20, output US$2.50 per million tokens. They are
not a default in this repo.

Hosted samples, all MEASURED, all small, none a success rate:

| Sample | Cases | Passed, three runs | Cost |
|---|---|---|---|
| main `3cbf6a7`, 2026-10-18 | 24 | 21/24, 21/24, 20/24 | US$0.052459, US$0.042210, US$0.032935. Total US$0.127604 ([COST.md](COST.md)) |
| main `684d7b7`, 2026-10-18 | 27 | 25/27, 25/27, 26/27 | US$0.055011, US$0.057835, US$0.052081. Total US$0.164927 (README) |
| Earlier 23-case sample, PR #1 | 23 | 18/23, 18/23, 19/23 | Not restated here. See [LIVE_SAMPLES.md](LIVE_SAMPLES.md) |

Open on the `684d7b7` sample: `edge_already_refunded` passed 0/3 (outcome
label only; nothing was written) and `edge_malformed_id` passed 1/3. The
README leaves both golden cases unchanged. v2 (`26155b5`) was 75/81
case-runs and v3 was 76/81. The README says that is not a clean improvement.

The README security list still says "The golden set is 24." The Results
table and `evals/results/latest.json` for the 2026-10-18 stub run say 27.
This plan uses 27 for the stub suite. The 24-case figure is the `3cbf6a7`
live sample, not the current cassette set.

## 4. ROI model

Formula, as [BUSINESS_CASE.md](BUSINESS_CASE.md) computes a day. Every
input is [EST]. The only measured money figures in the repository are the
stub micro-USD amounts and the small hosted samples above. They are not
this model's inputs.

**Assumptions [EST], each one already in [BUSINESS_CASE.md](BUSINESS_CASE.md):**

| Input | Value | Tag |
|---|---:|---|
| Refund requests per business day | 120 | [EST] |
| Analyst time today, per request | 6 minutes | [EST] |
| Analyst time with the agent, review only | 45 seconds = 0.75 minutes | [EST] |
| Loaded analyst cost | USD 28 / hour | [EST] |
| Production model cost per run | USD 0.01 | [EST], not measured |
| A wrong refund used as a scale check | USD 50 | [EST] |

**Arithmetic [EST]:**

- Hours avoided per business day = 120 × (6 − 0.75) / 60 = 10.5.
- Labor avoided = 10.5 × 28 = USD 294 per business day.
- Model bill = 120 × 0.01 = USD 1.20 per business day.
- Net before build cost and exceptions = 294.00 − 1.20 = USD 292.80 per
  business day. The repo rounds that to **about USD 290** [EST].
- Labor avoided per request = 294 / 120 = USD 2.45 [EST].
- One USD 50 wrong refund [EST] is 50 / 2.45 ≈ 20 requests of that labor
  saving. The business case states the same point as "many requests." It
  also says a refund above the order balance, or an email to the wrong
  address, costs more than a day of analyst time [EST]. This plan does not
  replace that sentence with a new incident cost.

**What this plan does not compute.**

- Business days per year are not in the repo. A year-1 multiple is
  **UNVERIFIED**. No day-count is inserted.
- Integration hours and a rate (identity provider, order system, mailer)
  are not in the repo. Initial investment is **UNVERIFIED**. Payback
  months are **UNVERIFIED**, because payback needs that investment.
- ROI = (benefit − cost) / cost is the formula. With build cost unknown,
  a year-1 percentage is not filled in. The daily net above is the model
  the repo actually wrote down.

**Two readings, both from the repo, not a new volume.**

| Reading | What is assumed | Per business day |
|---|---|---|
| Base [EST] | Review falls from 6 minutes to 45 seconds, and no exception refund is counted | About USD 290 net, from USD 292.80 before the repo's rounding |
| Falsifier [EST] | Review stays near 6 minutes because the draft is usually wrong ([BUSINESS_CASE.md](BUSINESS_CASE.md)) | Labor avoided ≈ USD 0. The USD 1.20 model bill [EST] remains. Net is negative before any wrong refund |

Other falsifiers already listed, with no extra dollars added here: approvers
stop reading, volume is far below 120/day [EST], or the system of record
cannot store an idempotency key. Those are discovery questions
([DISCOVERY.md](DISCOVERY.md)).

The stub does not belong in the ROI as a saving. One demo refund cost
**584 micro-USD** MEASURED on 2026-10-18 (v0.1.0, `stub-llm-v1`), and
**433 micro-USD** MEASURED on 2026-10-17. Both use the synthetic price.

## 5. Cost table

Operating day, [EST], from the assumptions in section 4. Not a quote.

| Item | Calculation | Amount | Tag |
|---|---|---:|---|
| Analyst time today | 120 × 6 / 60 hours | 12 hours / day | [EST] |
| Analyst time with the agent | 120 × 0.75 / 60 hours | 1.5 hours / day | [EST] |
| Labor avoided | 10.5 × USD 28 | USD 294 / day | [EST] |
| Model bill | 120 × USD 0.01 | USD 1.20 / day | [EST] |
| Net | 294 − 1.20, repo text "about USD 290" | USD 292.80 / day | [EST] |
| One wrong-refund scale check | stated as an average order | USD 50 | [EST] |
| Initial integration | not stated | none | UNVERIFIED |
| Shadow review of 30 drafts | named in [SCOPE.md](SCOPE.md), not done | none | UNVERIFIED |

Software costs this repository did record. The stub rows are a synthetic
price. The hosted rows are a sample, not a forecast.

| Item | When | Amount | Tag |
|---|---|---:|---|
| One demo refund, `make demo`, SIMULATED crash included | 2026-10-18, v0.1.0, `stub-llm-v1` | 584 micro-USD (3425 in / 124 out) | MEASURED |
| Same demo, earlier run | 2026-10-17, v0.1.0, `stub-llm-v1` | 433 micro-USD | MEASURED |
| Stub suite, 27 cases | 2026-10-18 | 12117 micro-USD | MEASURED |
| Per-run stub budget default | `RUN_BUDGET_MICRO_USD` | 100000 micro-USD (USD 0.10) | configured cap, not a measured spend |
| Three live suite runs, 24 cases, main `3cbf6a7` | 2026-10-18 | US$0.127604 total | MEASURED |
| Three live suite runs, 27 cases, main `684d7b7` | 2026-10-18 | US$0.164927 total, cap US$0.30 | MEASURED |
| OpenAI and Anthropic adapters against those APIs | — | no call from this repository | UNVERIFIED |

## 6. Measurement plan

Phases are the ones in [SCOPE.md](SCOPE.md). Durations in weeks are not
stated there, so none are added. Exit checks that this repository has not
performed stay UNVERIFIED.

1. **Phase 1, pilot, one reason code (`damaged`).** Shadow first: the agent
   drafts, a person compares, nothing is sent. Exit from shadow is a manual
   review of 30 drafts with no policy violation. This repository has not
   done that review. Then gated send, which is what the code does now.
   Exit also requires zero external effects without a recorded approval, a
   green golden set, a red `make eval-regression`, and a named backup.
2. **Phase 2.** Other reason codes, one at a time, each with new cases
   first. Postgres `FOR UPDATE SKIP LOCKED` only when more than one worker
   is needed. Not implemented (ADR 0001).
3. **Phase 3.** Operations owns the queue, the budget alert, and model
   changes. CI keeps replaying cassettes. A live run is a separate capped
   job. It does not replace the cassette gate.

What is checked on every pull request today, from `.github/workflows/ci.yml`
(this plan does not edit that file):

- `ruff`, `mypy`, and `pytest` with `--cov-fail-under=80`.
- `python -m agent_runtime.evalkit run` (cassette replay).
- `python -m agent_runtime.evalkit regression` must not exit 0.
- Secret scan. CI does not set `LIVE_MODE`.

Customer metrics in [METRICS.md](METRICS.md) stay empty until a person is
in the loop: approved without edit, policy violations that reach the
reviewer, queue age, cost per completed run including reviewer minutes,
and agreement between an LLM judge and a human. Do not invent a kappa.
Do not paste stub latency into a hosted row. Stub LLM-call p50 in
`latest.json` is 1 µs on 2026-10-18. That is in-process time, not an SLO.

At the end of a real pilot, the approver and the operator would confirm
the ledger (no ungated effect) and the shadow sample. That confirmation
has not happened. It is UNVERIFIED.

## 7. Risks

The register is [RISKS.md](RISKS.md). Likelihoods there are qualitative.
They are not measured rates. The rows that change this plan:

| Risk | Why it matters here | Mitigation already in the repo |
|---|---|---|
| Wrong amount, wrong order, or a refund before lookup | It wipes the [EST] labor saving | Policy re-check, `MAX_REFUND_CENTS` 100000, human gate, regression cassette |
| Prompt injection in the customer message | The six adversarial cases check invariants. A 2026-10-17 live run mostly ignored the injection, so those guards were barely exercised live | Tools block the effect. The invariant still passes if the model ignores the attack |
| Model claims `refund_completed` with no executed refund | The `684d7b7` sample still saw the claim. The nudge corrected it (16 nudges, 0 `needs_review`) | Nudge only for that claim, cap `MAX_COMPLETION_NUDGES` 2, then `needs_review`. The runtime does not create the write |
| Retry or crash pays twice | Payback math is irrelevant if the ledger double-pays | Effect key and the same-transaction ledger row. Tested. Not measured on a real order system |
| CI stays green across a model swap | The hosted sample is not 27/27 | Cassettes gate pull requests. A live run is capped and outside CI |
| Reviewer rubber-stamps | The 45-second [EST] becomes theater | "Approved without edit" is defined and empty. The product cannot force a person to read |
| SQLite stays the database by inertia | Fine at 120/day [EST] only as a pilot note | ADR 0001. Postgres is not implemented |
| Open live misses | `edge_already_refunded` 0/3 and `edge_malformed_id` 1/3 on `684d7b7` | Golden cases were not weakened. Cause not determined |

A failing eval is evidence. Loosening the case to go green is not a
mitigation ([RISKS.md](RISKS.md)).

## 8. What is MEASURED in this repo, and what is not

**MEASURED**

- Stub cassette suite on 2026-10-18, package 0.1.0, model `stub-llm-v1`:
  27/27, checker mean 1.00, threshold 0.80, 71356 in, 2453 out, 12117
  micro-USD, 2 completion nudges. Source:
  [evals/results/latest.json](../evals/results/latest.json).
- One `make demo` the same day: 3425 / 124 tokens, 584 micro-USD, status
  completed, one refund effect, one email effect, SIMULATED crash, both
  approvals. The 2026-10-17 demo was 433 micro-USD.
- The forced regression fails on a refund-before-lookup cassette.
- Ungated external effects in the stub suite: 0.
- Pytest on 2026-10-22, Python 3.12.3, pytest 9.1.1, package 0.1.0, Python
  sources at main `7ea9d66`: **110 passed** on four runs. Line coverage
  printed **88.05%** (2711/3079) on two runs and **87.82%** (2704/3079) on
  two runs. The seven statements are a lock race in
  `test_two_workers_cannot_execute_the_same_step`. The test passed each
  time. Command and the coverage warning are in the README Proof section.
- Hosted samples cited in section 3, with the commits and the "not a
  success rate" limit those pages already use.
- Synthetic price table and the integer per-step cost rule, in
  [COST.md](COST.md) and `src/agent_runtime/pricing.py`.

**Not measured (empty, [EST], or UNVERIFIED)**

- Analyst minutes, labor dollars, and the USD 0.01 production model price.
  All [EST].
- Approved without edit, queue age, reviewer minutes, and human agreement
  with an LLM judge.
- The 30-draft shadow review.
- A vendor invoice. OpenAI and Anthropic have not been called from this
  repository.
- Business days per year, integration cost, and payback.
- A success rate or an SLA from three hosted runs.
- Postgres `FOR UPDATE SKIP LOCKED`, OpenTelemetry, the customer's identity
  provider, and branch protection (a GitHub setting, not a file this plan
  changes).
- Latency as a service SLO. Stub microseconds are not a networked call.
