# Scope

A hypothetical engagement for Lumen Goods. No fee, no rate card, no real
statement of work. Phases exist so a pilot has a way to stop.

## Assumptions

- One reason code in the pilot: `damaged`. The other codes exist in the
  synthetic policy so the eval set can show them. They are not turned on for
  users in the pilot.
- One reviewer queue. One backup reviewer.
- The order system can store an idempotency key. If it cannot, the pilot
  stops. See discovery question 2.
- English only. Office hours. About 120 requests per business day [EST].
- No card data, no government ids.
- The model in production is chosen later. The pilot can run on the stub
  for integration, then on one named model behind the same interface.

## Out of scope

- Automatic refunds with no person.
- Chargebacks, partial returns of multi-item orders beyond a single amount,
  or exchanges.
- A second approver above a dollar threshold.
- Voice, chat on the storefront, or the customer writing free text as the
  only input. The runtime takes a structured request. The customer message
  is untrusted data inside that request.
- Multi-region, multi-tenant hosting.
- A legal opinion on refunds. The policy table is a stand-in.

## Phase 1 — Pilot

**Intent.** Prove the loop on `damaged` refunds without moving unexpected
money.

**What is built.** The runtime in this repo, pointed at a test order system
(here, the synthetic catalog). Reviewers use the CLI or the localhost API
behind the customer's identity provider. That identity provider is not in
this repo.

**Shadow, then gated send.**

1. Shadow: the agent drafts, a person compares the draft to what they would
   have done, and nothing is sent. Exit from shadow is a manual review of
   30 drafts with no policy violation. That review is a pilot activity.
   This repository has not done it.
2. Gated send: `send_refund` and `send_email` execute only after approval,
   which is what the code does today.

**Exit criteria (all of them).**

- Zero external effects without a recorded approval, checked from the ledger.
- The eval gate is green on the golden set, and a deliberate bad trajectory
  fails it (`make eval-regression`).
- The reviewer can name the backup and the rollback (previous prompt and
  cassettes).
- Drafts in shadow did not violate policy on the 30-draft review. Not
  measured in this repo.
- Cost per run is under a cap the customer sets. The stub's measured demo
  cost is 433 micro-USD (2026-10-17, v0.1.0, stub). A production cap is theirs
  to set. The code cap is `RUN_BUDGET_MICRO_USD`.

**Stop the pilot if** any ungated effect is observed, or the reviewer rejects
most drafts because the amount is wrong. Do not "fix" that by weakening the
eval.

## Phase 2 — Expand

Add the other reason codes already in the policy table, one at a time, each
with cases in the golden set before the code is allowed to propose them.

Add a second reviewer only if the queue age requires it. Move the ledger to
Postgres with `FOR UPDATE SKIP LOCKED` when more than one worker is needed.
Not before.

## Phase 3 — Steady state

Operations owns the queue, the budget alert, and the model-change checklist.
This repository's CI does not notice a model swap: it replays cassettes.
A live run, if they pay for one, is a separate job with a spend cap. If
they re-record cassettes, that diff is a pull request someone other than
the author merges. The live run does not replace the cassette gate.

Rollback of a bad prompt is a deploy of the previous revision. Refunds
already executed are reversed by a person in the order system, not by
replaying the agent.

## After handoff

See [RUNBOOK.md](RUNBOOK.md). The builder does not keep the approve button.
