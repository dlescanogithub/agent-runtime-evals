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
API. The optional client does that when `usage` is present.

| Scenario | Model | Tokens in / out | Cost | Latency | Quality | Price date |
|---|---|---|---|---|---|---|
| Eval suite, 22 cases, cassette replay | stub-llm-v1 | 31161 / 2059 | 5870 micro-USD for the suite | step p50 1 µs, p95 1433 µs | 22/22, judge mean 1.00 | Synthetic price, measured 2026-10-17 |
| One damaged-lamp refund, `make demo`, including a simulated crash and two approvals | stub-llm-v1 | 1836 / 124 | 348 micro-USD | in-process, not broken out as an SLO | completed, amount 4200 cents, both effects gated | Synthetic price, measured 2026-10-17 |
| Same refund on a hosted model | not run | not measured | not measured | not measured | not measured | Take the vendor page on the day you run it |
| Illustrative production day, 120 runs [EST] at USD 0.01 per run [EST] | unnamed | [EST] | USD 1.20 / day [EST] | [EST], not this repo | [EST] | Not a quote |

Latency is the time inside this process, around each step. The p95 of
1433 microseconds is 1.433 milliseconds. It will move if you re-run `make
eval` on another machine. It is not comparable to a networked model, where
almost all of the time is the model call.

Input tokens dominate because each model turn resends the transcript,
including the system prompt. That is normal for a chat API. Five turns on
the demo refund are why 1836 input tokens accompany 124 output tokens.

## Controls

| Control | Default | What it stops |
|---|---|---|
| `RUN_BUDGET_MICRO_USD` | 100000 (USD 0.10) | Another model call or tool after the run has spent more than the budget. The call that crossed the line is already paid for and recorded. Its side effects are not taken. |
| `MAX_STEP_ATTEMPTS` | 3 | Retries of a transient tool or model error. |
| `CIRCUIT_BREAKER_THRESHOLD` | 3 | A tool that keeps failing. A successful model call does not reset the counter. |
| `MAX_AGENT_STEPS` | 8 | A loop that never finishes. The happy path uses 5 model turns. |
| `RETRY_BACKOFF_MS` | 0 | Wait between retries. Zero so local tests are fast. Set it for a live provider. |

The refund amount has a separate ceiling in code: 100,000 cents per call,
and never more than the order's refundable balance. That is not the model
budget. Mixing them up is how a team accidentally caps the wrong thing.

## What a customer should do on day one

1. Write down the vendor price and the date.
2. Run the golden set once live, under a spend cap, and fill the empty row
   above. Do not paste the stub latency into that row.
3. Set `RUN_BUDGET_MICRO_USD` from the live number, with headroom for
   retries, not from the stub.
4. Alert on runs that end `budget_exceeded` or `circuit_open`.
