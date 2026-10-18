# Business case — Lumen Desk

Lumen Goods is a fictional home-goods retailer. Nothing here is a real
customer, a real catalog, or a measured saving. Runtime numbers cited from
this repo are labeled with the date and version. Everything else is [EST].

## Problem

Refund requests are handled by back-office analysts. The work is repetitive:
read the order, read the policy, decide an amount, write to the customer.
A demo of an agent looks finished. The failure mode that matters is quieter:
a prompt edit or a model swap refunds the wrong amount, skips the policy, or
emails the wrong person, and the first signal is a complaint.

The cost of that error is not the model bill. One refund above the order
balance, or one email to the wrong address, costs more than a day of
analyst time [EST].

## What the pilot actually automates

The agent may:

- read one order
- read the policy for one reason code
- propose `send_refund` and `send_email`

The agent may not:

- approve itself
- refund more than the policy amount
- email an address that is not on the order
- see a tool that lists other customers

A person still approves both external actions. The pilot does not remove
the analyst. It shortens the read-and-draft part and keeps the decision.

## ROI model [EST]

These inputs are a hypothetical discovery, not a measurement.

| Input | Value | Tag |
|---|---:|---|
| Refund requests per business day | 120 | [EST] |
| Analyst time today, per request | 6 minutes | [EST] |
| Analyst time with the agent, review only | 45 seconds | [EST] |
| Loaded analyst cost | USD 28 / hour | [EST] |
| Hours avoided per day | 120 × (6 − 0.75) / 60 = 10.5 | [EST] |
| Labor avoided per day | 10.5 × 28 = USD 294 | [EST] |
| Production model cost per run | USD 0.01 | [EST], not measured |
| Model bill per day at 120 runs | USD 1.20 | [EST] |
| Net before build cost and exceptions | about USD 290 / day | [EST] |

The only money figure this repository measured is the stub. On 2026-10-18,
version 0.1.0, model `stub-llm-v1`, one demo refund cost **584 micro-USD**
and the 27-case suite cost **12117 micro-USD**. That price is synthetic
($0.15 / 1M input tokens, $0.60 / 1M output tokens). It is not an OpenAI,
Anthropic, or other vendor invoice. See [COST.md](COST.md).

A wrong refund of an average order, say USD 50 [EST], wipes out the labor
saving of many requests. That is why the gate exists. The ROI only holds
if external effects stay behind a person and the policy re-check.

## Alternatives considered

| Option | Why it lost |
|---|---|
| Fully automatic refunds | The error cost is larger than the time saved. Out of scope for the pilot. |
| A chat window with no ledger | The next analyst cannot see what happened, and a crash retries blindly. |
| Prompt-only "never refund without approval" | A prompt is advice. The runtime refusing to execute is a control. |
| Blocking CI on a single live model call | Live calls are non-deterministic and cost money. Cassettes gate pull requests. A live run, if added later, is capped and nightly. |

## What would falsify this case

- Review time stays near 6 minutes [EST] because the draft is usually wrong.
- Analysts approve without reading, so the gate is theater.
- Volume is far below 120/day [EST], so the build cost is not recovered.
- The system of record cannot accept an idempotency key, so retries double-pay.

Those are discovery questions, not facts. See [DISCOVERY.md](DISCOVERY.md).
