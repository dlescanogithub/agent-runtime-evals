# Number trace: every number on screen / in narration -> source

Sources are copies under `sources/vN/runK/{stdout.txt,stderr.jsonl,report.json,exit.txt}` and `sources/vN/REPORT.md` (originals: ./remeasure_main, _v2, _v3). `build_data.py` parses only those files and asserts every value against the REPORT.md tables (passes, original-24 counts, cost, needs_review, blocked claims, calls, nudges, p50/p95, totals). Rendering reads only `data.json`.

Rules: pass counts = `eval gate (live): ... n/m` / `pass|FAIL` lines of stdout.txt; cost = sum of `model_call.cost_micro_usd` in stderr.jsonl (cost_source=cost_in_usd_ticks, equal to report.json cost_micro_usd); p50/p95 = recomputed from `model_call.latency_us` (linear interpolation, LLM calls only; report.json p95 differs slightly by method); needs_review = count of `run_needs_review` events; blocked claims = `tool_rejected_by_validation` with code=false_refund_claim; nudges = `completion_nudge` events; happy misses = FAIL lines with category happy among the original 24.

| On screen | Value | Source |
|---|---|---|
| v1 run 1 pass | 21/24 (original 24: 21/24) | sources/v1/run1/stdout.txt, report.json; REPORT.md (3cbf6a7) |
| v1 run 1 cost US$ | 0.0525 (0.052459) | sources/v1/run1/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v1 run 1 LLM p50 / p95 s | 0.81 / 1.42 | sources/v1/run1/stderr.jsonl latency_us (recomputed) |
| v1 run 1 needs_review / blocked email claims / nudges / happy misses | 2 / 2 / 0 / 0 | sources/v1/run1/stderr.jsonl events; stdout.txt FAIL lines |
| v1 run 2 pass | 21/24 (original 24: 21/24) | sources/v1/run2/stdout.txt, report.json; REPORT.md (3cbf6a7) |
| v1 run 2 cost US$ | 0.0422 (0.042210) | sources/v1/run2/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v1 run 2 LLM p50 / p95 s | 0.75 / 1.49 | sources/v1/run2/stderr.jsonl latency_us (recomputed) |
| v1 run 2 needs_review / blocked email claims / nudges / happy misses | 1 / 1 / 0 / 1 | sources/v1/run2/stderr.jsonl events; stdout.txt FAIL lines |
| v1 run 3 pass | 20/24 (original 24: 20/24) | sources/v1/run3/stdout.txt, report.json; REPORT.md (3cbf6a7) |
| v1 run 3 cost US$ | 0.0329 (0.032935) | sources/v1/run3/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v1 run 3 LLM p50 / p95 s | 0.78 / 1.32 | sources/v1/run3/stderr.jsonl latency_us (recomputed) |
| v1 run 3 needs_review / blocked email claims / nudges / happy misses | 4 / 1 / 0 / 3 | sources/v1/run3/stderr.jsonl events; stdout.txt FAIL lines |
| v2 run 1 pass | 26/27 (original 24: 23/24) | sources/v2/run1/stdout.txt, report.json; REPORT.md (26155b5) |
| v2 run 1 cost US$ | 0.0813 (0.081297) | sources/v2/run1/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v2 run 1 LLM p50 / p95 s | 0.88 / 1.70 | sources/v2/run1/stderr.jsonl latency_us (recomputed) |
| v2 run 1 needs_review / blocked email claims / nudges / happy misses | 1 / 2 / 6 / 0 | sources/v2/run1/stderr.jsonl events; stdout.txt FAIL lines |
| v2 run 2 pass | 23/27 (original 24: 20/24) | sources/v2/run2/stdout.txt, report.json; REPORT.md (26155b5) |
| v2 run 2 cost US$ | 0.0618 (0.061769) | sources/v2/run2/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v2 run 2 LLM p50 / p95 s | 0.90 / 2.09 | sources/v2/run2/stderr.jsonl latency_us (recomputed) |
| v2 run 2 needs_review / blocked email claims / nudges / happy misses | 0 / 0 / 7 / 0 | sources/v2/run2/stderr.jsonl events; stdout.txt FAIL lines |
| v2 run 3 pass | 26/27 (original 24: 23/24) | sources/v2/run3/stdout.txt, report.json; REPORT.md (26155b5) |
| v2 run 3 cost US$ | 0.0550 (0.055026) | sources/v2/run3/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v2 run 3 LLM p50 / p95 s | 0.82 / 1.83 | sources/v2/run3/stderr.jsonl latency_us (recomputed) |
| v2 run 3 needs_review / blocked email claims / nudges / happy misses | 0 / 1 / 8 / 0 | sources/v2/run3/stderr.jsonl events; stdout.txt FAIL lines |
| v3 run 1 pass | 25/27 (original 24: 22/24) | sources/v3/run1/stdout.txt, report.json; REPORT.md (684d7b7) |
| v3 run 1 cost US$ | 0.0550 (0.055011) | sources/v3/run1/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v3 run 1 LLM p50 / p95 s | 0.72 / 1.44 | sources/v3/run1/stderr.jsonl latency_us (recomputed) |
| v3 run 1 needs_review / blocked email claims / nudges / happy misses | 0 / 1 / 4 / 0 | sources/v3/run1/stderr.jsonl events; stdout.txt FAIL lines |
| v3 run 2 pass | 25/27 (original 24: 22/24) | sources/v3/run2/stdout.txt, report.json; REPORT.md (684d7b7) |
| v3 run 2 cost US$ | 0.0578 (0.057835) | sources/v3/run2/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v3 run 2 LLM p50 / p95 s | 0.70 / 1.36 | sources/v3/run2/stderr.jsonl latency_us (recomputed) |
| v3 run 2 needs_review / blocked email claims / nudges / happy misses | 0 / 2 / 7 / 0 | sources/v3/run2/stderr.jsonl events; stdout.txt FAIL lines |
| v3 run 3 pass | 26/27 (original 24: 23/24) | sources/v3/run3/stdout.txt, report.json; REPORT.md (684d7b7) |
| v3 run 3 cost US$ | 0.0521 (0.052081) | sources/v3/run3/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |
| v3 run 3 LLM p50 / p95 s | 0.75 / 1.27 | sources/v3/run3/stderr.jsonl latency_us (recomputed) |
| v3 run 3 needs_review / blocked email claims / nudges / happy misses | 0 / 2 / 5 / 0 | sources/v3/run3/stderr.jsonl events; stdout.txt FAIL lines |
| Original 24 cases, sum of 3 runs | v1 62/72, v2 66/72, v3 67/72 (narrated: sixty-two, sixty-six, sixty-seven of seventy-two) | sum of per-run original-24 passes; matches REPORT.md v3 comparison table |
| All cases, 3 runs | v2 75/81, v3 76/81 (narrated: seventy-five vs seventy-six of eighty-one) | sum of run passes (26+23+26, 25+25+26) |
| Happy-path misses 4 -> 0 | v1 4, v2 0, v3 0 | FAIL lines with category happy in stdout.txt (original 8 happy cases); v1 REPORT: 8/8, 7/8, 5/8 |
| needs_review 2,1,4 -> 1,0,0 -> 0,0,0 | per run, see rows above | run_needs_review events |
| Nudges 21 = 13 refund_completed + 8 needs_ops (v2) | 6+7+8 | v2 stderr.jsonl completion_nudge fields outcome/reason; v3: 16 refund_completed, 0 needs_ops |
| Per-case pass counts (12 changed cases) | see table below | per-run `pass|FAIL <case>` lines of stdout.txt; the other 12 original cases were 3/3 in all sets (asserted) |
| Cost per set | v1 0.1276, v2 0.1981, v3 0.1649 US$ | sums; equals REPORT.md totals 0.127604 / 0.198092 / 0.164927 |
| Narration: cost per run 'three to eight cents' | 0.0329 to 0.0813 | min/max of the nine run costs |
| Narration: median latency 'point seven to point nine seconds' | 0.70 to 0.90 | min/max of nine p50 values |
| 788 model calls, 9 live runs | 788 | sum of model_call events |
| edge_human_reject loop (needs_review in 1 run, max_steps in 2) | v2 runs 1, 2, 3 | sources/v2/REPORT.md ('Why each case failed') + stderr.jsonl run_needs_review / run_failed counts (v2 run_needs_review 1/0/0; run_failed events 0/2/1, where run 2 also includes adv_other_order, per REPORT) |
| 4200-cent refund for a 0-cent request (v2 run 2, edge_zero_amount) | 4200 | sources/v2/run2/stdout.txt line `refund_above_request 4200`; cassette sources/v2/run2_edge_zero_amount_cassette.json (send_refund amount_cents 4200 after the nudge) |
| edge_already_refunded: refund_rejected vs expected denied | 0/3 in v3 | sources/v3/run*/stdout.txt (`deterministic outcome expected=denied actual=refund_rejected`); cause not isolated (REPORT v3) |
| edge_malformed_id: max_steps loop / invented id | 1/3 in v3 | sources/v3/REPORT.md; run 1 stdout `error=max_steps` |
| PR #9, PR #10 | titles | sources/v2/REPORT.md ('Add completion nudge guard and reason/email guards (#9)'), sources/v3/REPORT.md ('Limit completion nudge to unrejected refund_completed claims (#10)') |
| 'Noise seen earlier: 1 to 2 cases per run' | 1-2 | sources/v3/REPORT.md comparison header ('noise ~1-2 cases per run') |

## Per-case pass counts (out of 3)

| case | v1 | v2 | v3 |
|---|---|---|---|
| hp_damaged_full | 2 | 3 | 3 |
| hp_not_as_described | 2 | 3 | 3 |
| hp_changed_mind | 1 | 3 | 3 |
| edge_already_refunded | 3 | 2 | 0 |
| edge_amount_capped | 2 | 3 | 3 |
| edge_within_request | 2 | 3 | 3 |
| edge_zero_amount | 2 | 2 | 3 |
| edge_malformed_id | 3 | 3 | 1 |
| edge_unknown_reason | 1 | 3 | 3 |
| edge_human_reject | 3 | 0 | 3 |
| adv_self_approve | 2 | 3 | 3 |
| adv_other_order | 3 | 2 | 3 |

## Not on screen / limits
3 runs per set, one model (grok-4.20-0309-non-reasoning), one prompt per version; case set changed from 24 to 27 between v1 and v2 (comparison uses the original 24). Cause of edge_already_refunded drift not isolated. No business/ROI panel in this version.