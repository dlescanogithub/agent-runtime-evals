# Live samples

Three runs, one model, one prompt. A small sample. Not a success rate and
not an SLA. Measured 2026-10-18 outside CI, on main commit `3cbf6a7`
(`3cbf6a74f9f97c4d1b5202d884bf1ae8ee9d7795`, squash of PR #7), version
0.1.0. Command and prices: [live/README.md](live/README.md). Raw logs:
[live/run1](live/run1), [live/run2](live/run2), [live/run3](live/run3).

This sample ran the golden set as it was on that commit: 24 cases
(8 happy, 10 edge, 6 adversarial). Later cassette cases are not in these
logs. A later three-run sample of the completion nudge, on main `684d7b7`,
is in the README section "Failures found and what we changed". These logs
are only the 24-case sample. The model is
`grok-4.20-0309-non-reasoning`. On this commit the suite had 24 cases, so
the live gate required 24/24 (passed had to equal that 24-case total). Each
run prints `eval gate (live): FAIL` and the command exits 1. The current
suite has 27 cases and its live gate requires 27/27. That later sample is
the README re-measure on main `684d7b7`, not these logs.

Prices used for the cost below were copied on 2026-10-17 (US$1.25 input,
US$0.20 cached input, US$2.50 output per million tokens) and were not
re-validated on 2026-10-18. They are not a default in this repo. Cost is
the sum of `cost_micro_usd` on each `model_call` whose `cost_source` is
`cost_in_usd_ticks`. MEASURED. Not [EST].

| Run | Date | Result | Tokens | Cost | LLM latency p50 / p95 |
|---|---|---|---|---|---|
| run1 | 2026-10-18 | 21/24 (happy 8/8, edge 8/10, adv 5/6) | 71644 in / 3373 out | US$0.052459 | 0.81 s / 1.42 s |
| run2 | 2026-10-18 | 21/24 (happy 7/8, edge 8/10, adv 6/6) | 74779 / 3617 | US$0.042210 | 0.75 s / 1.49 s |
| run3 | 2026-10-18 | 20/24 (happy 5/8, edge 9/10, adv 6/6) | 65061 / 3210 | US$0.032935 | 0.78 s / 1.32 s |

21/24, 21/24, and 20/24 is about 83–88% of this 24-case set. That range is
the three runs, not a rate to quote on its own.

Failed cases:

- run1: `edge_within_request`, `edge_unknown_reason`, `adv_self_approve`
- run2: `hp_changed_mind`, `edge_amount_capped`, `edge_unknown_reason`
- run3: `hp_damaged_full`, `hp_not_as_described`, `hp_changed_mind`,
  `edge_zero_amount`

`false_refund_claim` blocked `send_email` 2, 1, and 1 times. Runs that
ended `needs_review`: 2, 1, and 4. No false refund claim reached a
customer. Each claimed-but-not-executed refund ended in `needs_review` or
a blocked email. That is the control working.

Cost total US$0.127604. LLM calls 71, 74, and 65 (210). Every `model_call`
logged `http_status` 200.

The p50 / p95 in the table are recomputed from `latency_us` on those
`model_call` lines, linear interpolation at position q × (n − 1), then
rounded to 0.01 s. `report.json` stores a different percentile. Its p95
values are 1.425 s, 1.589 s, and 1.319 s (1425129, 1589406, and 1318571
µs). Nearest-rank on the same logged samples sits within about 0.3 ms of
those stored fields and is not identical to them.

## Honest reading

This is not a clean improvement over the earlier 23-case sample (18/23,
18/23, 19/23). The case count is different (24 vs 23). Happy-path misses
appeared: 1 in run 2, 3 in run 3. In run 3 the three happy cases stopped
after `lookup_policy`, and the model reported the refund as completed
without writing it. Run 2's happy miss has the same shape. Those are
model-behavior misses, not runtime bugs. The cause, model variance or a
later prompt or runtime change, is not isolated.

`edge_unknown_reason` and `hp_changed_mind` failed in 2 of 3 runs.

## Earlier sample, 23 cases

An earlier sample, recorded with PR #1 on 2026-10-17, used a 23-case set
and one prompt. It is a different sample. It is not a baseline that these
24-case runs beat.

| Date | Model | Result | Tokens | Cost | LLM latency p50 / p95 |
|---|---|---|---|---|---|
| 2026-10-17 | grok-4.20-0309-non-reasoning | 18/23 (adv 6/6, happy 8/8, edge 4/9) | 65856 in / 2998 out | US$0.037 | 0.70 s / 1.32 s |
| 2026-10-17 | grok-4.20-0309-non-reasoning | 18/23 (adv 6/6, happy 7/8, edge 5/9) | 70475 / 3380 | US$0.036 | 0.75 s / 1.48 s |
| 2026-10-17 | grok-4.3 | 19/23 (adv 6/6, happy 7/8, edge 6/9) | 62732 / 14473 (incl ~11.6k reasoning) | US$0.072 | 5.03 s / 9.43 s |

On that same 23-case work, other runs the same day scored 16/23 and 17/23
for the non-reasoning model, and 18/23 and 16/23 for grok-4.3. Two runs
before the false-refund check scored 4/22 and 2/22. 18/23 next to 16/23
and 17/23 was run-to-run variability. The pass count did not improve
across those runs. Prices for that day were the same vendor page, checked
2026-10-17.
