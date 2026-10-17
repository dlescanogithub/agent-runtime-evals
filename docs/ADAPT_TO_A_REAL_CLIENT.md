# Adapting this to a real customer

One page. Lumen Goods is fictional. Nothing below is a measurement from a
real account. Numbers you have not run stay [EST] or blank.

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
