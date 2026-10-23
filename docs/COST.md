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
unless `LIVE_MODE=1`. The hosted sample in the README is three runs on
2026-10-18. It is a small sample, not a success rate, and it does not
measure every later commit.

| Scenario | Model | Tokens in / out | Cost | Latency | Quality | Price date |
|---|---|---|---|---|---|---|
| Eval suite, 27 cases, cassette replay | stub-llm-v1 | 71356 / 2453 | 12117 micro-USD for the suite | p50 1 µs on 2026-10-18. p95 is in the report and is not a gate. | 27/27, checker mean 1.00, completion_nudges=2 | Synthetic price, measured 2026-10-18 |
| One damaged-lamp refund, `make demo`, including a simulated crash and two approvals | stub-llm-v1 | 3425 / 124 | 584 micro-USD | in-process, not broken out as an SLO | completed, amount 4200 cents, both effects gated | Synthetic price, measured 2026-10-18 |
| Same refund desk on a hosted model | grok-4.20-0309-non-reasoning, main `3cbf6a7`, 2026-10-18, 24-case suite | [LIVE_SAMPLES.md](LIVE_SAMPLES.md) | US$0.032935–0.052459 per suite run. Total US$0.127604 across three runs. | LLM p50 0.75 s to 0.81 s, recomputed from the call logs. See LIVE_SAMPLES.md. | 21/24, 21/24, 20/24 on that 24-case suite. Three runs, one prompt, not a success rate. That commit's live gate required 24/24, so each run exits 1. The current 27-case suite's live gate requires 27/27. | Prices dated 2026-10-17, not re-validated on 2026-10-18. US$1.25 in / US$0.20 cached / US$2.50 out per million tokens. Not a default in this repo. |
| Illustrative production day, 120 runs [EST] at USD 0.01 per run [EST] | unnamed | [EST] | USD 1.20 / day [EST] | [EST], not this repo | [EST] | Not a quote |

Stub latency is in-process and is not an SLO. On 2026-10-17, `make eval`,
version 0.1.0, model `stub-llm-v1`, the report's LLM-call p50 was 1 µs.
Tool-step latency is a separate field in `evals/results/latest.json`.
Tests do not compare either field. Neither number is a networked model call.

Input tokens dominate because each model turn resends the transcript,
including the system prompt. That is normal for a chat API. Five turns on
the demo refund are why 3425 input tokens accompany 124 output tokens.

## Live mode price table

Live mode is off unless `LIVE_MODE=1`. CI does not set it. Vendor prices are
not stored here. Copy them from the provider's page into the environment on
the day you measure. A measured xAI sample from 2026-10-18 is in
[LIVE_SAMPLES.md](LIVE_SAMPLES.md) (three runs, one prompt, not a
success rate). The rates used that day were copied on 2026-10-17 and were
not re-validated on 2026-10-18. Those prices are not defaults and they are not copied into
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

The hosted sample in [LIVE_SAMPLES.md](LIVE_SAMPLES.md) is main `3cbf6a7`,
command `PYTHONPATH=src python3 -m agent_runtime.evalkit live`, measured
2026-10-18. Three runs, one prompt, not a success rate. An earlier 23-case
sample (18/23, 18/23, 19/23) is labelled there as PR #1. A later 27-case
sample on main `684d7b7` (same date, same model, three runs, total
US$0.164927) is in the README section "Failures found and what we changed".
The row above stays the 24-case sample. The OpenAI and
Anthropic adapters have not been called against those APIs from this
repository. CI does not call any hosted API. See [RUNBOOK.md](RUNBOOK.md).

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
