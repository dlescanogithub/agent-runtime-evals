# Discovery questions

Ten questions to ask before building this for a real customer. Lumen Goods
is fictional. The "answer we used" column is a hypothetical discovery, marked
as such. The last column is the point: the answer changes the design.

## 1. What decision does the agent take, and what does a wrong one cost?

**Why it matters.** The cost of the error decides whether a human gate is
optional or mandatory.

**Hypothetical Lumen answer.** The agent proposes a refund. A wrong refund
pays money that is hard to claw back. A wrong email exposes another
customer's address. [hypothetical]

**Design change.** `send_refund` and `send_email` are the only external
tools, and both stop for a person. Read tools do not. If the action had been
"draft a reply that a person always sends", the email tool would not exist.

## 2. What is the system of record?

**Why it matters.** The agent cannot be the place money is remembered.

**Hypothetical Lumen answer.** The order system is the record. This service
may only request a refund with an idempotency key. [hypothetical]

**Design change.** The effect log dedupes on a business key
(`order + amount + reason`), not on a key the model invents. The MVP stores
that log in SQLite. Production would write the same key into the order
system. ADR 0001 and ADR 0005.

## 3. What is the daily volume?

**Why it matters.** Volume picks the queue, the budget, and whether a single
worker is honest.

**Hypothetical Lumen answer.** About 120 requests per business day, office
hours, no overnight spike. [EST] [hypothetical]

**Design change.** A single worker and SQLite are enough to demonstrate the
loop. The production note is Postgres `FOR UPDATE SKIP LOCKED` so more
workers can be added without double-claiming a run. At 120/day we would not
start with a distributed queue.

## 4. What is the manual process today, and what is its error rate?

**Why it matters.** The baseline is the thing the pilot has to beat. If we
do not know the error rate, we cannot claim an improvement.

**Hypothetical Lumen answer.** An analyst reads the order in the admin tool,
checks a written policy, and types the refund. Errors are mostly the wrong
amount or a refund after the window. The rate is not known. [hypothetical]

**Design change.** The pilot measures "approved without edit" and "policy
violations in the draft", not a made-up accuracy percent. The tool re-checks
the window so a model mistake does not become a payment. We do not claim a
before/after error rate in this repo.

## 5. Who approves?

**Why it matters.** Someone has to own the queue, including when they are
out.

**Hypothetical Lumen answer.** One senior analyst approves during the pilot.
A backup is named. The agent has no approve tool. [hypothetical]

**Design change.** Approve and reject are API and CLI actions outside the
model. The runbook names the owner and the backup. If the answer had been
"two people must agree above USD 100 [hypothetical]", the gate would be a second step, not
a boolean. That is out of scope until they ask.

## 6. What sensitive data does it touch?

**Why it matters.** It decides what may be logged, what the model may see,
and what an email may contain.

**Hypothetical Lumen answer.** Order id, item, amount, and the customer's
email on that order. No payment card, no government id. [hypothetical]

**Design change.** Traces store latency, tokens, cost, tool name, and order
id. They do not store the email or the body. The email tool rejects any
address that is not on the order, and any body that mentions another order
id. Logs at INFO follow the same rule.

## 7. What happens when the model changes?

**Why it matters.** This is the failure the customer already had: a silent
behavior change.

**Hypothetical Lumen answer.** They want to try a cheaper model next quarter.
They cannot take a week of bad refunds to find out. [hypothetical]

**Design change.** Pull requests replay cassettes. They do not call the
new model, so a model swap is invisible until someone re-records. That
re-record is future work. Today the gate checks the runtime against the
frozen stub: trajectory, schema, amounts, gates, and a code checklist
under 0.80. See ADR 0003.

## 8. What SLO is acceptable?

**Why it matters.** A refund desk is not a voice agent. Seconds are fine.
A stuck approval queue is not.

**Hypothetical Lumen answer.** A draft in under a minute is enough. A run
must not sit in `waiting_review` overnight without an owner. [hypothetical]

**Design change.** The stub's in-process latency is not the SLO. On
2026-10-17, `make eval`, v0.1.0, the LLM-call p50 was 1 µs. Tool-step
latency is a separate field and neither one is a gate. The SLO we would
write with them is about queue age and failed runs, not model milliseconds.
The circuit breaker and the per-run budget are the controls for a stuck or
runaway loop.

## 9. How do you measure "good"?

**Why it matters.** If "good" is "the demo felt right", the project has no
exit test.

**Hypothetical Lumen answer.** A good draft is one the analyst approves
without changing the amount, the reason, or the recipient. A bad draft is a
policy violation that reaches the reviewer, or a refund that was not gated.
[hypothetical]

**Design change.** The golden set encodes that definition: trajectory,
amount, gate, and "no other customer's order id". The customer-facing metric
(approved without edit) is defined in [METRICS.md](METRICS.md) and is **not**
measured here, because there is no human panel.

## 10. Who owns the agent in production?

**Why it matters.** After handoff, someone restarts it, reads the queue, and
rolls back a bad prompt.

**Hypothetical Lumen answer.** Operations owns the queue and the on-call.
The person who changes prompts does not approve their own rollout.
[hypothetical]

**Design change.** [RUNBOOK.md](RUNBOOK.md) splits operator, approver, and
the person who merges a prompt change. Rollback is "ship the previous
cassette and prompt", not "ask the model to undo the refund". Branch
protection on `main` is part of that ownership. This repo documents the
required checks and does not turn them on itself.
