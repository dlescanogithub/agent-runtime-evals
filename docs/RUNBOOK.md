# Runbook — Lumen Desk

Who does what after this is handed to a customer's operations team.
Lumen Goods is fictional. Names of roles are roles, not people.

## Roles

| Role | Does | Does not |
|---|---|---|
| Operator | Runs the process, watches the queue, restarts after a crash, rolls back a deploy | Approve refunds. Edit the policy table to clear a queue. |
| Approver | Approves or rejects `send_refund` and `send_email`. Has a named backup. | Merge a prompt change. Share the API port. |
| Change owner | Opens the pull request that changes a prompt, a policy rule, or a cassette | Approve their own merge. Approve the refunds that result from it. |

On a small team one person may hold two roles on different days. They do
not hold change-owner and approver on the same change.

## Operating

Default process, from a checkout:

```bash
make setup
make demo          # synthetic story, wipes var/demo each time
python -m agent_runtime.cli serve
```

`serve` binds `API_HOST` and `API_PORT` (default `127.0.0.1:8080`). There is
no authentication. Keep it on localhost, or put the customer's identity
provider in front of it and do not publish the raw port.

Start a real run (still the stub unless the environment says otherwise):

```bash
python -m agent_runtime.cli run --input examples/refund_damaged.json
python -m agent_runtime.cli show --run-id <id>
python -m agent_runtime.cli approve --run-id <id> --step-id <id>
python -m agent_runtime.cli reject --run-id <id> --step-id <id> --reason "outside policy"
python -m agent_runtime.cli resume --run-id <id>
```

The ledger file is `DATABASE_PATH` (default `var/runtime.sqlite`).
`make demo` deletes `var/demo` first so the story repeats. A normal run
does not. A second refund of the same order, amount, and reason returns the
original effect. A second run that looks the order up first should see a
zero balance and deny.

Configuration is environment variables only. See `.env.example`. There is
no config file with secrets.

## Monitoring

Today the signals are local:

- run status: `running`, `waiting_review`, `completed`, `failed`, `interrupted`
- step rows: attempts, tokens, cost, error
- JSON logs on stderr (status changes, tool name, order id, not the email)
- JSONL traces under `TRACE_DIR` (latency, tokens, cost)

Watch these. They are the MVP's monitors:

| Signal | Why | Response |
|---|---|---|
| Steps sitting in `waiting_review` | The queue is the product | Approver or backup. If the age is over the agreed limit, page the approver. The limit is a customer decision. This repo does not set one. |
| Runs in `failed` with `budget_exceeded` | A loop or a prompt got expensive | Stop traffic. Read the steps. Do not raise the budget to hide it. |
| Runs in `failed` with `circuit_open` | A dependency is failing | Check the order system. Do not retry by hand in a loop. |
| Runs in `interrupted` | The worker stopped between steps | `resume`. Safe. |
| Effect count higher than approved refunds | Something double-paid | Stop the worker. Compare `effects` to approvals. The key should have prevented this. Treat it as an incident. |

OpenTelemetry is not wired. The trace fields are the ones an exporter would
send later: event, run id, step id, tool name, latency, tokens, cost.

## Incident: a refund went out that should not have

1. Stop the worker. Do not resume the queue.
2. Read the run. Note whether a person approved, and whether `send_refund`
   returned `executed` or a policy denial.
3. If money moved, a person reverses it in the order system. The agent does
   not have an automatic undo. The effect key means a retry will not pay a
   second time. It will also not unpay.
4. Keep the run row. It is the evidence.
5. If the cause was a prompt or a model, roll back that deploy (below)
   before turning the worker on.
6. Add a case that would have failed CI, in a reviewed change. Do not only
   patch production.

## Incident: the worker died mid-tool

`resume` the run. If the effect row exists, the tool returns it. If it does
not, the tool tries again, up to the attempts that are left. Do not delete
the step to "unstick" it. That is how a second payment gets invented.

## Approval-gate ownership

- The approver looks at order id, amount, reason, and recipient.
- The approver rejects when the amount is not what they would have typed.
- The backup is named before the pilot sends anything.
- The change owner is not the approver for refunds produced by a change
  they just shipped, during the first day of that change. Someone else
  reads the queue.

## Rollback

A bad prompt or a bad cassette:

1. Deploy the previous revision. The previous cassettes and the previous
   policy function come back together.
2. Runs already `waiting_review` stay waiting. The approver rejects them
   if the draft is from the bad revision. Do not bulk-approve a queue you
   do not trust.
3. Runs already `completed` are not rewritten. Reversal is a human action
   in the order system.

A bad dependency (order system down):

1. Leave runs `failed` or let the circuit open.
2. Fix the dependency.
3. `resume` only the runs that stopped mid-tool. Do not start duplicates.

There is no feature flag service in this MVP. Rollback is "the previous git
revision".

## Model change

1. Run the golden set against the new model outside CI, under a spend cap
   the operator sets. This repo does not do that run for you.
2. Review the cassette diff. A trajectory change is a product change.
3. Someone who did not write the diff merges it. `main` requires the CI
   jobs listed in SECURITY.md. Those checks are a GitHub setting. This
   repository does not turn them on.
4. Watch `budget_exceeded`, queue age, and rejections for the first day.

## Handoff checklist

The builder walks through this once, then leaves the approve button.

- [ ] Operator can start, show, resume, and read a failed run.
- [ ] Approver and backup can approve and reject, and know they are accountable.
- [ ] The API is not reachable off the host without the identity provider.
- [ ] `DATABASE_PATH` and `TRACE_DIR` are on a disk the operator controls.
- [ ] Secrets are in the environment, not in the repo. `.env.example` has no values that work.
- [ ] `make eval` is green on the revision being handed over, and `make eval-regression` is red.
- [ ] The customer has written their own price into COST.md's empty row, or accepted that they have not measured a live model yet.
- [ ] Rollback was rehearsed once: deploy the previous revision, reject a waiting draft, confirm no second effect.

After that, the change owner is whoever the customer names. The builder does
not keep a standing approve role.
