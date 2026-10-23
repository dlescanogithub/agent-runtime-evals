# How it works

A walkthrough for engineers and buyers.
Lumen Goods is a fictional retailer. The orders are synthetic. There is no
data from a real customer.

The point of this text is to explain the system from end to end without
reading the code at the same time. If a number below is not marked
MEASURED, it is [EST] or it is not a number.

## In one sentence

It is a back-office agent that proposes refunds, and it does not move money
or send an email until a person approves. Every step is stored in a
database. If the process dies, it resumes. If someone changes the model and
the agent skips a lookup, CI does not allow the merge.

## The problem, in plain words

In a demo the agent "works". The problem shows up later: the prompt or the
model changes, the agent refunds too much or writes to someone else, and
the team finds out when the customer complains. There is no record of what
it did, and no cost cap per run.

This repo shows how to avoid that, at a small scale.

## What each module does

Each box has one responsibility.

| Module | What it does | What it does not do |
|---|---|---|
| `cli.py` / `api.py` | Start a run, approve, reject, resume | Do not decide policy |
| `demo.py` | Tells the story: crash, resume, approve | Deletes its own database so the story can be repeated |
| `runner.py` | The loop. Each turn does one thing | Does not hide state in memory |
| `history.py` | Rebuilds the transcript by reading the steps | Is not a second source of truth |
| `providers/fake.py` | The local model. Reads `customer_message` | Does not call the network |
| `providers/cassette.py` | Replays recorded responses | Does not decide anything new |
| `providers/openai_compatible.py` | HTTP POST in the OpenAI format. Used for xAI or OpenAI | Off unless `LIVE_MODE=1`. CI does not use it. Hosted samples are outside CI |
| `providers/anthropic.py` | Thin adapter to the Anthropic Messages API | Same rules: opt-in and a spend cap. The measured hosted sample in this repo is xAI, not this adapter |
| `tools.py` | Validates arguments and runs the four tools | Does not approve |
| `gate.py` | The list of tools that stop: `send_refund`, `send_email` | Is not a prompt |
| `policy.py` | The business rule, pure: same data, same decision | Does not touch the database |
| `catalog.py` | The synthetic orders, read only | Refunds are not written here |
| `store.py` | SQLite: runs, steps, effects, ledger | Is not Postgres |
| `trace.py` | One JSONL per run: latency, tokens, cost | Does not store the email or the body |
| `evalkit/` | The 27 cases, the cassettes, the deterministic checker | Does not call a paid model. `make eval-live` is separate and does not run in CI |

## The four tools

1. `lookup_order` reads an order. It does not stop.
2. `lookup_policy` reads the day window for a reason. It does not stop.
3. `send_refund` is an external effect. It stops until a person says yes.
4. `send_email` is an external effect. It stops. The recipient has to be
   the email on that order, at `@lumen-goods.example`.

There is no `approve` tool. If there were, the model could approve itself.

## One run, end to end

The example is `make demo`: order `LG-1001`, reason `damaged`,
4200 cents. The lamp arrived broken. All of it is synthetic.

1. The CLI creates a `runs` row with status `running` and the input as JSON.
2. The runner asks the provider for a turn. The stub does not "think": it
   looks at which tools were already called. With no lookup yet, it asks
   for `lookup_order`.
3. That turn is stored as a step. In the demo, the run is cut there on
   purpose (`interrupted`). That is the crash between two steps.
4. `resume` does not call the model again for that turn. It reads the step
   and continues. It runs `lookup_order`. The catalog returns Avery Chen's
   order. The email stays in the database, not in the trace.
5. The stub asks for `lookup_policy`. The `damaged` rule is 30 days. The
   order is 5 days old. It continues.
6. The stub asks for `send_refund` for 4200, which is the balance, not an
   invented number. The runner validates the arguments and, because the
   tool is in `gate.py`, inserts a `waiting_review` step and stops. There
   is still no row in `effects`. The money has not moved.
7. A person approves by CLI or by the API. That does not execute yet.
   `resume` executes. `send_refund` runs `policy.decide` again. If the
   amount is not what the policy allows, it writes nothing. If it matches,
   it writes the effect and adds to the ledger in the same transaction.
8. The stub asks for `send_email` to the email on the order. The gate
   stops it again.
9. After the second approval, the stub closes with a small JSON object:
   `outcome`, `order_id`, `amount_cents`, `customer_summary`. The run
   ends `completed`.

In the 2026-10-18 measurement (`make demo`, version 0.1.0, model
`stub-llm-v1`) that story, with the cut and the two approvals, used 3425
input tokens, 124 output tokens, and 584 micro-USD at the synthetic price.
It is not a vendor invoice.

If the person rejects the refund, the step stays `rejected`, the model
receives that result, and the stub closes on `refund_rejected`. The effect
is not written. The case `edge_human_reject` accepts another label, for
example `denied`, when there was no effect, `send_refund` went through the
gate, and the text to the customer does not say the refund already happened.

## What happens if it dies in the middle of the tool

The step stays `running` and the attempt counter is already stored. On
resume, it retries with the attempts that remain. If the effect was already
written, the tool returns that receipt and does not add again. Order
matters: look up the effect first, then re-check the policy. The other way
around, the second attempt sees a zero balance and looks like a rejection,
even though the money already moved.

## Why each decision

**The model is not trusted.** The stub reads `customer_message`. If the
text says to skip the lookup, inflate the amount, or send the email
somewhere else, the stub obeys. The tool or the gate stops it, and no
effect is written. That tests the controls against this stub. It does not
test a real model: CI only replays cassettes.

**The gate is in code, not in the prompt.** A prompt that says "do not
refund without approval" helps. A branch that does not run the tool until
an approve arrives through the API is stronger. The model has no way to
call that approve.

**The runtime computes the idempotency key.** If the model picks it, two
retries can be two payments. The key is the tool plus the business
arguments (order, amount, reason).

**SQLite now, Postgres later.** A demo and CI do not need a server. The
tables are shaped for the production design: a worker that takes a run
with `SELECT … FOR UPDATE SKIP LOCKED` so two workers do not take the same
one. That is written in ADR 0001 and it is not implemented. Do not describe
it as running.

**Cassettes in CI.** A live call costs money and is not deterministic. CI
replays the stub's recorded responses. The tools and the gate do run for
real. Recording again is a diff that a person reviews, not an automatic
step. Changing the model in production, without re-recording, does not turn
CI red. The gate does not see that change.

**Two eval levels.** The deterministic checks (trajectory, schema, amounts,
effects, gate) always block. The checker is a checklist in code and blocks
if the score falls under 0.80. It is not a judge and it does not call a
model. An LLM judge is future work. There is no human-agreement number.
Do not invent one.

**Budget and circuit breaker are different things.** The budget is model
spend (micro-USD). The refund cap is something else (the order balance and
a maximum of 100000 cents). The circuit breaker counts consecutive tool
failures. A successful model turn does not reset it, because a model that
keeps calling a broken tool would reset it every time.

**Traces do not carry the email.** If they are exported to a collector
later, a second redaction pass should not be required. The body and the
recipient stay in SQLite, which is the local trust boundary.

## What a buyer is told

A person reads the order, reads the policy, and types the refund. This
runtime does not remove that person. The agent does the reading and
proposes the amount. The person approves or rejects. If the process dies,
it does not pay twice. If the model changes tomorrow, the same case set
has to stay green or the change does not ship.

The ten questions in [DISCOVERY.md](DISCOVERY.md) change the design, in
this order:

- If a mistake costs money, there is a gate. If the agent only drafts text
  that a person always sends, the email is not even a tool.
- If the system of record does not accept an idempotency key, the pilot
  does not start.
- If the volume is an office (in the hypothetical case, 120 per day
  [EST]), do not start with a distributed queue. Write down when that
  would be warranted.
- If they do not know today's error rate, do not promise an improvement.
  Measure "approved without edit" in the pilot.
- If the approver has no backup, do not turn on sending.

The rollout is in [SCOPE.md](SCOPE.md):

1. Shadow. The agent proposes, the person compares, nothing is sent. Leave
   shadow with 30 drafts reviewed by hand and no policy violation. That is
   pilot work. This repo did not do it.
2. Gated send. Only then does `send_refund` hit their system.
3. Only after that, more refund reasons, one at a time, each with new
   cases in the golden set.

The handoff is in [RUNBOOK.md](RUNBOOK.md). The person who builds it does
not keep the approve button. Operations operates. The approver approves.
The person who changes the prompt does not merge that change alone.

Savings stay in two columns. Stub cost is measured (584 micro-USD for the
demo, 12117 micro-USD for the 27-case suite, on 2026-10-18). Hour savings
are [EST] and live in the business case, with the assumptions in view. The
two columns are not mixed.

## Use cases, governance, and strategy

The README has a fixed section: "Use cases, governance and business
strategy". The detail for adapting the runtime is in
[ADAPT_TO_A_REAL_CLIENT.md](ADAPT_TO_A_REAL_CLIENT.md). In short:

This repo implements one case: the Lumen Desk refund desk. The agent
proposes. `send_refund` and `send_email` stop until a person approves or
rejects. `lookup_order` and `lookup_policy` only read. If the model says
`refund_completed` and there is no matching effect, and nobody rejected
`send_refund` or `send_email` on that run, the runtime hands the
inconsistency back (`completion_nudge`, cap `MAX_COMPLETION_NUDGES`, 2)
and does not write the refund on its own. `denied`, `needs_ops`, and
`refund_rejected` do not get that nudge. If it keeps saying the refund
already happened, the run ends `failed` with `needs_review`. That detector
is a fixed list of English phrases. It is a heuristic, not a guarantee: a
paraphrase, or another language, is not matched. If the person rejects, as
in `edge_human_reject`, no effect is written.

The other cases in the README are sketches, not code. A ticket agent that
classifies and does not tell the customer until the queue owner approves.
A scheduling agent that does not book, move, or cancel until the calendar
owner says yes. A personal expense assistant that proposes a payment and
does not move money. A personal mail assistant that drafts and does not
send. In all four, a person approves the effect. The model has no approve
button. None of them names a real customer, employer, or project, and none
of them brings a real volume or a real price.

Governance, in this repo, is pointed at by files:

- Controls: typed tools and least privilege in `tools.py`, an amount cap
  in `policy.py`.
- Human gate: `gate.py`.
- Traces: one JSONL per run in `trace.py`, with the run id, without the
  email body. Adversarial cases check invariants, not the stub's exact
  tool list.
- Risks: [RISKS.md](RISKS.md).
- Cost and caps: [COST.md](COST.md).
- Incident and rollback: [RUNBOOK.md](RUNBOOK.md).

It does not cover the customer's identity provider, OpenTelemetry, Postgres
with `SKIP LOCKED`, or a model judge.

Business strategy keeps two columns. Hour savings are in
[BUSINESS_CASE.md](BUSINESS_CASE.md) and are [EST] (about USD 290 per
business day [EST], on 120 orders per day [EST]). Scope and phases, with
exit criteria, are in [SCOPE.md](SCOPE.md): shadow, then gated send, then
more reasons one at a time. What was measured is in
[METRICS.md](METRICS.md): on 2026-10-18 the stub passed 27/27. Customer
metrics (approved without edit, queue age) are defined and empty. In a
Deployment Strategist conversation the order is shadow, then gate, the
builder does not keep the button, and CI tests the runtime.

## Questions engineers and buyers ask

### Runtime

**Where is the state if the process dies?**
In SQLite. The runner remembers nothing: each turn reads the run.
`interrupted` is a cut between steps. `running` on a step is a cut in the
middle of the tool.

**Why does it not pay twice?**
Because the business key is already written. The second attempt reads the
effect and returns the same receipt. The ledger does not add again.

**What if the model skips the lookup but the amount is correct?**
The tool rejects `send_refund` if that run did not have a successful
`lookup_order` and `lookup_policy`. It does not open the gate and it does
not write an effect. The case `adv_skip_lookup` expects exactly that, and
it passes. The forced regression uses the same kind of cassette against
the happy case, which expects a completed refund, so the gate stays red.
The two measure different things: one, that the control stops the attack;
the other, that a bad transcript does not slip through as a happy case.

**Does the stub show that GPT or Claude are safe?**
No. It shows the runtime against recorded responses. A real model is not
in CI. Re-recording cassettes would be a reviewed diff, and this repo does
not do that against a paid model. A live run, if someone pays for it, is
separate and capped.

**Why is stub latency in microseconds?**
Because it is time inside the process, with a stub. It is not a model on
the network. The report separates model calls (`latency_us_p50` /
`latency_us_p95`) from tool steps. On the stub both stay in microseconds
and neither is an SLO. Live model-call latency, in seconds, is in the
README and comes from three runs on 2026-10-18 on `main` `3cbf6a7`. It is
not a success rate.

### Deployment

**How does this go to production without risking refunds?**
Shadow first, gate second. One reason (`damaged`). An approver with a
backup. Zero effects without a recorded approval is an exit criterion.
If one appears, sending is turned off.

**What does the customer's IT provide?**
A place to run the process, the model secret in the environment (not in
the repo), an order system that accepts an idempotency key, and the
identity provider in front of the API. This MVP requires a bearer token
(`API_TOKEN`) on everything except `GET /health`. That does not replace
the customer's login.

**Who owns the gate?**
The approver. The person who changes the prompt does not approve the
refunds from their own change on the first day. The backup is named before
sending is turned on. After the handoff, the person who built it does not
keep the button.

**How is the pilot measured?**
In CI: the golden set green and the forced regression red. With people:
drafts approved without editing the amount, the reason, or the recipient,
and queue age. This repo does not publish an "accuracy" it did not
measure. There is no agreement number between a judge and a human, because
there is no judge: the checker is code.

**What if they change the model?**
This repo's CI does not notice. It only sees cassettes. Trying the new
model is a separate run, with a spend cap, and a cassette diff that
someone who did not write it reviews. The 2026-10-18 live sample is in the
README: three runs, one model, not a success rate. CI still does not call
it. `main` can require the `ci` job. That check is configured on GitHub.
The repo does not turn it on by itself. Rollback is deploying the previous
revision and rejecting whatever is still waiting. Money already sent is
reversed by a person in the order system. The agent has no magic undo.

**What if the customer wants the gate removed to go faster?**
The cost of a wrong refund is set next to the 45-second saving [EST]. If
they still want the gate removed, that is outside this scope. It is not a
hidden flag.

**What does it cost?**
The default path costs nothing: stub and cassettes. A live model is not in
CI. The stub's synthetic price is in COST.md so the ledger adds up. A
vendor price is copied from the official page on the day it is measured.
This repo does not contain that number, because that run was not done.

**What does it not do?**
It has a bearer token, not the customer's identity provider. It does not
export OpenTelemetry. It does not run two workers with `SKIP LOCKED`. It
does not have 100 cases. It does not have an LLM judge. It does not promise
a measured ROI. The business case marks [EST] on what is estimated.

**How is it left running?**
With the runbook: who watches the queue, which signal is an incident, how
to resume a `running` step, how to roll back, and a handoff checklist.
The last line is that the builder does not stay on as the approver.
