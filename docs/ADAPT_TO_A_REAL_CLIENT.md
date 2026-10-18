# Adapting this to a real customer

Lumen Goods is fictional. Nothing below is a measurement from a real
account. Numbers you have not run stay [EST] or blank. Only the refund
desk is implemented. The other use cases are sketches of the same loop.

## What to keep

- The loop: one step at a time, state in the ledger, resume from the row.
- The human gate on anything that leaves the process (here, refund and email).
- Tool checks that do not trust the model: argument shape, the order on the
  ticket, a lookup before a refund, policy re-checked at execution, the
  effect key computed by the runtime.
- Cassettes in CI for the runtime. They do not test the customer's model.
- The deterministic checker as a checklist in code. Do not call it a judge.
- The runbook roles: operator, approver, backup, change owner. The person
  who ships a change is not the approver on day one.

## What to swap

| Piece in this repo | Replace it with |
|---|---|
| `catalog.py` synthetic orders | The customer's order system, read-only at first |
| `send_refund` / `send_email` writing a local row | Their refund API and their mailer, both idempotent |
| SQLite | Postgres, with `FOR UPDATE SKIP LOCKED`, when more than one worker runs |
| `API_TOKEN` bearer check | Their identity provider. Keep the bearer check until that is in front. |
| `FakeProvider` and the cassettes | Their model, only outside CI, under a spend cap they set |
| `pricing.py` synthetic rates | The vendor price on the day you measure |
| `policy.py` windows | Their written policy, after someone signs it |
| JSONL traces | Their collector, still without email and body |

Do not swap the gate for a sentence in the prompt.

## Discovery inputs

Take the ten questions in [DISCOVERY.md](DISCOVERY.md) into the first
working session. The answers that change the design are: which actions
move money or message a customer, who may approve, what the system of
record is, and what "good" means in their words. Write the answers down.
If an answer is a guess, mark it [EST] or hypothetical. Do not paste a
number from this repo into their slide.

## Rollout gates

1. **Pilot.** One reason code, one queue, shadow mode (drafts only, no
   effect). Exit when a named approver has reviewed a sample they agreed
   in advance, and when zero effects have been written without an approval
   row. This repository has not done that review.
2. **Expand.** Turn on the real refund and email calls, still behind the
   gate. Exit when the queue has an owner and a backup, the spend cap has
   been hit in a drill, and a rollback (previous revision, reject the
   waiting drafts) has been rehearsed once.
3. **Steady state.** They own the queue. A model change is a separate live
   run they pay for, plus a reviewed cassette diff if they choose to record
   one. This repo's CI will not do that run for them.

Stop the pilot if an effect appears without an approval, or if the approver
cannot explain a draft they approved.

## What this repo will not do for them

It will not call their model, invent their ROI, or record their demo GIF.
[HOW_IT_WORKS.md](HOW_IT_WORKS.md) is the explanation. [RUNBOOK.md](RUNBOOK.md)
is the handoff.

## Use-case sketches

The short table is the README section "Use cases, governance and business
strategy". This page says what you would swap. None of these sketches name
a real client, employer, or project.

### Implemented: back-office refund agent

Lumen Desk is the code in this repo.

- **Problem.** A model that can call a refund API will eventually refund
  the wrong order or the wrong amount, and may tell the customer it did
  so before any money moved.
- **Who approves.** A named person, through the CLI or the localhost API.
  The model has no approve tool. On day one the person who ships the
  prompt is not that approver. See the roles in [RUNBOOK.md](RUNBOOK.md).
- **Gated effects.** `send_refund` and `send_email` in
  `src/agent_runtime/gate.py`. `lookup_order` and `lookup_policy` only read.
- **What the runtime does.** `tools.py` checks argument shape, the order
  on the ticket, a successful lookup of both the order and the policy
  before a refund, and the recipient against the order. `policy.py` caps
  the amount at `MAX_REFUND_CENTS` (100000 cents) and at the refundable
  balance, and `send_refund` runs that check again at execution.
  `runner.py` refuses to close a run as `refund_completed` unless an
  executed refund matches the order and the amount; otherwise the run is
  `failed` and the error starts with `needs_review`. `edge_human_reject`
  shows a rejection: zero effects and a gate on `send_refund`. The outcome
  label is not the control. The stub cassette still says `refund_rejected`.

For a real retailer, swap the rows in "What to swap" above. Keep the gate.

### Design only: ticket triage and routing

- **Problem.** Misrouted work, or a note that reaches a customer before a
  person has read it.
- **Who approves.** The queue owner, before a customer-facing send or a
  close that notifies someone. A silent internal label can stay ungated
  if they accept that risk in writing.
- **Gated effects.** Send, and close-with-notify. Read-ticket and
  draft-reply stay open, the way lookups stay open here.
- **How this runtime would handle it.** Put those effect names in the
  same frozenset `gate.py` uses. Require a lookup of the ticket before
  the send, the way `send_refund` requires `lookup_order` and
  `lookup_policy`. Bind the recipient to the address on the ticket, the
  way `send_email` binds to the order. Do not add an approve tool.
- **Not in this repo.** There is no ticket catalog, no router, and no
  second policy table. Building it means a new catalog module and new
  eval cases, including a human rejection with zero effects.

### Design only: appointment scheduling

- **Problem.** A double book, or a cancellation the attendee did not ask
  for.
- **Who approves.** The person who owns the calendar.
- **Gated effects.** Create, reschedule, cancel. Reading free/busy stays
  open.
- **How this runtime would handle it.** The runner already stops on the
  gate list and resumes only after `approve` or `reject`. A reject ends
  the run with no effect, as `edge_human_reject` does for refunds. The
  effect key would be the slot plus the attendee, so a retry does not
  book twice. That key is computed by the runtime, not by the model.
- **Not in this repo.** No calendar client, no slot catalog.

### Design only: personal-finance assistant

- **Problem.** An assistant that categorizes expenses is useful. The same
  process must not move money because the model said so.
- **Who approves.** The account holder. There is no second queue, but
  there is still a gate. "I am the only user" is not a reason to let the
  model call pay.
- **Gated effects.** Transfer, pay, or any tool that moves money.
  Categorize and summarize stay open.
- **How this runtime would handle it.** Same propose-and-hold loop, same
  per-run budget, same rule that a claimed "paid" outcome requires a
  matching effect row. A personal deploy still loads `LLM_API_KEY` from
  the environment and still sets `MAX_LIVE_SPEND_USD` before `LIVE_MODE=1`.
- **Not in this repo.** No bank or card adapter. No real balances. Do not
  put credentials in the repo to try one.

### Design only: personal inbox assistant

- **Problem.** Drafts are cheap. A send to the wrong thread is not.
- **Who approves.** The mailbox owner, on each send.
- **Gated effects.** Send. Draft and label stay open.
- **How this runtime would handle it.** Mirror `send_email`: the model
  proposes the call, the runtime holds it, and the recipient has to match
  a record the tool loaded (the thread's participants), not a string the
  model invented. A rejection writes no effect.
- **Not in this repo.** No mail store. The only sender path is the
  synthetic `send_email` to `@lumen-goods.example`.

## Governance when you adapt

Keep the checklist. Point each line at their system, not at a slide.

| Practice | In this repo | They still have to |
|---|---|---|
| Typed tools, least privilege, caps | `tools.py`, `policy.py` (`MAX_REFUND_CENTS`), read-only `catalog.py` | Name which of their APIs are reads and which move money or message a person. Cap amounts in code, not in the prompt. |
| Human approval | `gate.py`, ADR 0002, `edge_human_reject` | Name the approver and a backup before the first real effect. The builder does not keep the button. |
| Traceability | `trace.py` JSONL, run ids, `needs_review` in `runner.py`, invariants in `evalkit/checks.py` | Keep run ids. Keep bodies out of the trace. Keep the invariant that a success claim requires the effect row. |
| Risk register | [RISKS.md](RISKS.md) | Add their systems of record and who pages when an effect lands without an approval. |
| Cost controls | [COST.md](COST.md), `RUN_BUDGET_MICRO_USD`, `MAX_LIVE_SPEND_USD` | Copy prices from the vendor page on the measurement date. Set the cap in the environment. Do not commit it. |
| Incident and rollback | [RUNBOOK.md](RUNBOOK.md) | Rehearse deploy-previous plus reject-waiting-drafts once before expand. Money already sent is reversed in their order system by a person. |

Still not covered, here or by adapting the docs alone: their identity
provider, OpenTelemetry, Postgres `FOR UPDATE SKIP LOCKED`, an LLM judge,
a human-agreement number, and a live score. The live-sample table is three
runs on main `3cbf6a7` (2026-10-18, 24 cases). See [LIVE_SAMPLES.md](LIVE_SAMPLES.md).
Three runs are a small sample, not a success rate, and they do not measure
later commits.

## Business strategy when you adapt

Use their words for the problem. Do not paste Lumen Goods volumes into
their deck.

- **ROI.** [BUSINESS_CASE.md](BUSINESS_CASE.md) is an illustrative model:
  about USD 290 per business day [EST] on 120 requests/day [EST], model
  bill USD 1.20/day [EST]. The only measured costs in this repo are stub
  costs on 2026-10-17 (`make demo` 433 micro-USD, `make eval` 7371 micro-USD,
  `stub-llm-v1`). Rebuild the table with their volume, their loaded
  cost, and a price copied from the vendor page. Mark every unmeasured
  cell [EST].
- **Scope.** [SCOPE.md](SCOPE.md). Pilot one action (here, `damaged`).
  Shadow exit is a manual review of 30 drafts with no policy violation.
  This repo has not done that review. Gated send exits only when the
  ledger shows zero effects without an approval, the golden set is green,
  and `make eval-regression` is red. Expand one action at a time.
- **Metrics.** [METRICS.md](METRICS.md). Quote the stub 24/24 only as a
  runtime check on 2026-10-17. Customer metrics (approved without edit,
  queue age) start empty.
- **Deployment Strategist conversation.** The pitch is the control loop,
  not a model name: shadow, then a gate, CI on cassettes, a spend cap
  before any live call, and a handoff where operations owns the queue.
  Discovery questions that change the design are in
  [DISCOVERY.md](DISCOVERY.md).
