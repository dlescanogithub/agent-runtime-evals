# ADR 0002 — A human gate for external effects

## Status

Accepted.

## Context

`lookup_order` and `lookup_policy` only read. `send_refund` and `send_email`
would move money or contact a person. A prompt that says "wait for approval"
is not a control. The model can be instructed, by the user or by a bad
prompt edit, to ignore it.

## Options

1. Let the model call an `approve` tool. Rejected. That is the model
   approving itself.
2. Gate every tool, including reads. Rejected. Reviewers will rubber-stamp
   lookups, and the queue becomes noise.
3. Gate only the tools in an explicit set, in code. Chosen.

## Decision

`gate.py` lists `send_refund` and `send_email`. The runner inserts a step
with status `waiting_review` and returns. Nothing is executed. Approve and
reject are CLI and API calls. Reject writes a tool result the model can
see, and the model is not allowed to retry that action on its own. The stub
stops. A real model might try again. The effect key and the policy check
still apply.

Validation failures never reach the reviewer. A bad email address or an
amount above the hard cap is a tool error, not a queue item.

## Consequences

- The happy path cannot finish inside `start`. The caller has to approve.
  The eval harness approves on purpose, and it records that it saw the gate
  first. If the runtime ever executes without that pause, the case fails.
- The API has no login. The gate is only as strong as the network in front
  of it. Localhost is the MVP. A deployment puts the customer's identity
  provider in front. See the runbook.
