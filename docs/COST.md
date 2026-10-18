# Cost and latency

## What was measured

Date: 2026-10-17. Version: 0.1.0. Model: `stub-llm-v1` (local fake provider
and cassette replay of that provider). Price: synthetic, defined in
`src/agent_runtime/pricing.py`.

| | Input | Output |
|---|---:|---:|
| Synthetic price | 150,000 micro-USD per 1,000,000 tokens | 600,000 micro-USD per 1,000,000 tokens |
| In USD, for humans | $0.15 / 1M tokens | $0.60 / 1M tokens |

This is **not** a price from a vendor page. It exists so a run has a cost
the report can add up. A production table replaces these two numbers with
the provider's page on the day you measure, and says so.

Cost is computed per step with integer division, then summed. Do not
recompute from the token totals and expect the same integer.

Token estimate for the stub: about 4 characters per token. Stable, so
cassettes do not drift. A real provider would use the usage field from the
API. The optional client does that when `usage` is present. That client is off
unless `LIVE_MODE=1`. A few live runs on 2026-10-17 are in the README.
They are not a success rate, and they do not measure every later commit.

| Scenario | Model | Tokens in / out | Cost | Latency | Quality | Price date |
|---|---|---|---|---|---|---|
| Eval suite, 24 cases, cassette replay | stub-llm-v1 | 41302 / 2026 | 7371 micro-USD for the suite | p50 1 µs on 2026-10-17. p95 is in the report and is not a gate. | 24/24, checker mean 1.00 | Synthetic price, measured 2026-10-17 |
| One damaged-lamp refund, `make demo`, including a simulated crash and two approvals | stub-llm-v1 | 2408 / 124 | 433 micro-USD | in-process, not broken out as an SLO | completed, amount 4200 cents, both effects gated | Synthetic price, measured 2026-10-17 |
| Same refund desk on a hosted model | grok-4.20-0309-non-reasoning and grok-4.3, pre-squash SHA `c1efdfd` on branch `cursor/agent-runtime-evals-mvp-7e58` only | [LIVE_SAMPLES.md](LIVE_SAMPLES.md) | US$0.036–0.072 per suite run on 2026-10-17 | LLM p50 0.70 s to 5.03 s. See LIVE_SAMPLES.md. | 18/23, 18/23, 19/23. A few runs, one prompt, not a success rate. Not a rerun of later commits. | [docs.x.ai/developers/models](https://docs.x.ai/developers/models), 2026-10-17. US$1.25 in / US$0.20 cached / US$2.50 out per million tokens. Not a default in this repo. |
| Illustrative production day, 120 runs [EST] at USD 0.01 per run [EST] | unnamed | [EST] | USD 1.20 / day [EST] | [EST], not this repo | [EST] | Not a quote |

Stub latency is in-process and is not an SLO. On 2026-10-17, `make eval`,
version 0.1.0, model `stub-llm-v1`, the report's LLM-call p50 was 1 µs.
Tool-step latency is a separate field in `evals/results/latest.json`.
Tests do not compare either field. Neither number is a networked model call.

Input tokens dominate because each model turn resends the transcript,
including the system prompt. That is normal for a chat API. Five turns on
the demo refund are why 2408 input tokens accompany 124 output tokens.

## Live mode price table

Live mode is off unless `LIVE_MODE=1`. CI does not set it. Vendor prices are
not stored here. Copy them from the provider's page into the environment on
the day you measure. A measured xAI sample from 2026-10-17 is in
[LIVE_SAMPLES.md](LIVE_SAMPLES.md) (a few runs, one prompt, not a
success rate). Those prices are not defaults and they are not copied into
the client:

| Provider | Where to copy the price | Base URL the client appends to |
|---|---|---|
| xAI (Grok), OpenAI-compatible | [docs.x.ai models](https://docs.x.ai/docs/models), or the models page linked from the xAI docs if that path moves | `https://api.x.ai/v1` plus `/chat/completions` |
| OpenAI | [platform.openai.com pricing](https://platform.openai.com/docs/pricing) | `https://api.openai.com/v1` plus `/chat/completions` |
| Anthropic (thin adapter) | [Claude pricing docs](https://platform.claude.com/docs/en/about-claude/pricing) | `https://api.anthropic.com` plus `/v1/messages` |

| Setting | Value in this repo | What to put |
|---|---|---|
| `LLM_PRICE_DATE` | empty | `YYYY-MM-DD` of the page you copied |
| `LLM_INPUT_USD_PER_MILLION` | empty | USD per 1,000,000 input tokens, from that page |
| `LLM_OUTPUT_USD_PER_MILLION` | empty | USD per 1,000,000 output tokens, from that page |
| `MAX_LIVE_SPEND_USD` | empty | Hard cap in USD, per run and per process |
| `LLM_API_KEY` | empty | Secret, in the shell only. Never in the repo or in CI |

The client converts those USD strings to integer micro-USD (6 decimal places
max). A zero price is rejected, because it would disable the cap. This
estimate is not an invoice. The provider's bill is the source of truth.

Output tokens are `max(completion_tokens, total_tokens - prompt_tokens)` when
`total_tokens` is present. That counts reasoning tokens a provider bills
outside `completion_tokens`, once, and it does not add them again when they
are already inside `completion_tokens`. If `total_tokens` is missing and
`reasoning_tokens` is present, they are added and the log sets
`reasoning_assumed_extra`.

If `usage.cost_in_usd_ticks` is present, 1 tick = 1e-10 USD, the spend cap
uses that bill rounded up to the next micro-USD. The token table is not
applied on top. That bill already includes the provider's cache discount
and reasoning.

Cached input (`prompt_tokens_details.cached_tokens`, or Anthropic
`cache_read_input_tokens`) uses `LLM_CACHED_INPUT_USD_PER_MILLION` when you
set it, from the same official page. If cached tokens are reported and that
price is empty, and the API did not send cost ticks, those tokens are priced
at the full input rate and the log says `token_table_cached_as_uncached`.
That is an upper bound. It is not silent, and it is not the invoice.
Anthropic cache writes are added to input tokens and priced at the uncached
input rate. This repo does not invent a write multiplier.

`MAX_LIVE_SPEND_USD` is checked before the call and again after the cost is
added. If the call crosses the cap, the HTTP request may already have been
sent. The completion is discarded and the run fails with a spend-cap error.
It is not retried. The same cap applies to the run and to the process, so a
second run in the same process stops too.

`RUN_BUDGET_MICRO_USD` is the older per-run budget on recorded step cost.
Hosted calls write the operator's price into that ledger as well. Set both.
The stub suite does not use the live table. Its cost stays the synthetic
one in `pricing.py`.

The hosted sample in [LIVE_SAMPLES.md](LIVE_SAMPLES.md) is pre-squash
SHA `c1efdfd` (branch `cursor/agent-runtime-evals-mvp-7e58`), command
`python -m agent_runtime.evalkit live`, measured 2026-10-17. A few runs,
one prompt, not a success rate. The OpenAI and Anthropic adapters have not
been called against those APIs from this repository. CI does not call any
hosted API. See [RUNBOOK.md](RUNBOOK.md).

## Controls

| Control | Default | What it stops |
|---|---|---|
| `RUN_BUDGET_MICRO_USD` | 100000 (USD 0.10) | Another model call or tool after the run has spent more than the budget. The call that crossed the line is already paid for and recorded. Its side effects are not taken. |
| `MAX_LIVE_SPEND_USD` | unset. Live mode is off. | Hosted calls only, and only after `LIVE_MODE=1`. One cap for the run and one for the process. The completion that crosses it is not used. |
| `MAX_STEP_ATTEMPTS` | 3 | Retries of a transient tool or model error. |
| `CIRCUIT_BREAKER_THRESHOLD` | 3 | A tool that keeps failing. A successful model call does not reset the counter. |
| `MAX_AGENT_STEPS` | 8 | A loop that never finishes. The happy path uses 5 model turns. |
| `RETRY_BACKOFF_MS` | 0 | Wait between tool retries. Zero so local tests are fast. Hosted model retries use the capped backoff in the runbook, not this setting. |

The refund amount has a separate ceiling in code: 100,000 cents per call,
and never more than the order's refundable balance. That is not the model
budget. Mixing them up is how a team accidentally caps the wrong thing.

## What a customer should do on day one

1. Write down the vendor price and the date in `LLM_PRICE_DATE`,
   `LLM_INPUT_USD_PER_MILLION`, and `LLM_OUTPUT_USD_PER_MILLION`.
2. Run one case live, under `MAX_LIVE_SPEND_USD`, and fill the empty row
   above. Do not paste the stub latency into that row. This repo has not
   done that run.
3. Set `RUN_BUDGET_MICRO_USD` from the live number, with headroom for
   retries, not from the stub.
4. Alert on runs that end `budget_exceeded` or `circuit_open`.
