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

`serve` binds `API_HOST` and `API_PORT` (default `127.0.0.1:8080`). It does
not start unless `API_TOKEN` is set. Callers send `Authorization: Bearer`.
`GET /health` does not need the token. Keep the process on localhost, and
put the customer's identity provider in front before any other host can
reach it. Approving a step that is already approved does nothing.

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
not, the tool tries again, up to the attempts that are left, but only when
`claim_token` is still null. A second live worker loses the run lock and
does not execute. If the process died inside the loop, `run_locks` still
has a row and resume will not steal it. Confirm the worker is dead, delete
that one `run_locks` row, clear `claim_token` if it is set, and resume
once. Do not delete the step to "unstick" it. That is how a second payment
gets invented.

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

## Enable live mode

Live mode is off. CI runs the stub and the cassettes only. The hosted
client in this repo has **not** been called against the real xAI, OpenAI,
or Anthropic API. Diego is the person who would do that, on a machine that
is not CI, after he loads a key as a secret.

Do not put the key in the repo, in a cassette, in a prompt, in a log, or in
the workflow file. `.env.example` lists the names and leaves the values
empty.

xAI (Grok) is the OpenAI-compatible provider. The shell below is the shape,
not a command that contains a key. Replace the secret-manager line with the
one your store actually uses.

```bash
# This process only. The key never lands in a file in the repo.
export LLM_API_KEY="$(your-secret-manager read lumen-xai-key)"
export LIVE_MODE=1
export LLM_PROVIDER=xai
export LLM_BASE_URL=https://api.x.ai/v1
export LLM_MODEL="<model id from the xAI docs>"
export LLM_PRICE_DATE="<YYYY-MM-DD of the pricing page>"
export LLM_INPUT_USD_PER_MILLION="<USD per 1M input tokens, from that page>"
export LLM_OUTPUT_USD_PER_MILLION="<USD per 1M output tokens, from that page>"
export MAX_LIVE_SPEND_USD="1.00"
```

`LIVE_MODE` must be the exact value `1`. `true` leaves it off, and a hosted
provider without `1` refuses to start. `LLM_PROVIDER=fake` cannot be
combined with live mode.

OpenAI uses the same client with `LLM_PROVIDER=openai` and
`LLM_BASE_URL=https://api.openai.com/v1`. Anthropic is a thin adapter:
`LLM_PROVIDER=anthropic` and `LLM_BASE_URL=https://api.anthropic.com`
(the client appends `/v1/messages` and sends `anthropic-version: 2023-06-01`).
Prices for those providers come from their own pages. See
[COST.md](COST.md). Do not copy the stub's synthetic price into these
variables.

What the cap does:

- `MAX_LIVE_SPEND_USD` applies to each run and to the whole process.
- A call that would cross either one raises a spend-cap error. The run
  fails. The completion is not used, so no tool runs from it. The HTTP
  request may already have been sent, so the provider may still bill those
  tokens.
- A second cap in the same process is a configuration error. Restart the
  process to change it.
- Logs are one JSON object per call: provider, model, run id, HTTP status,
  tokens, cost, latency, and `LLM_PRICE_DATE`. They do not include the
  prompt, the response body, or the key.

Until Diego runs the commands above against the real API, treat live mode
as untested. A green CI job does not mean a hosted model was called.

## Model change

1. The cassette gate will not notice the new model. A live run is a
   separate job, under `MAX_LIVE_SPEND_USD`. This repo does not do that
   run for you, and it has not been run against the real API.
2. If you re-record cassettes, review the diff. A trajectory change is a
   product change. CI keeps passing the old cassettes until that diff lands.
3. Someone who did not write the diff merges it. `main` requires the CI
   jobs listed in SECURITY.md. Those checks are a GitHub setting. This
   repository does not turn them on.
4. Watch `budget_exceeded`, spend-cap failures, queue age, and rejections
   for the first day.

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
