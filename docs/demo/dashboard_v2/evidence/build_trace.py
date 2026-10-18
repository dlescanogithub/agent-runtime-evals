import json
d=json.load(open("data.json")); R=d["runs"]; C=d["cases"]
L=["# Number trace: every number on screen / in narration -> source","",
"Sources are copies under `sources/vN/runK/{stdout.txt,stderr.jsonl,report.json,exit.txt}` and `sources/vN/REPORT.md` (originals: ./remeasure_main, _v2, _v3). `build_data.py` parses only those files and asserts every value against the REPORT.md tables (passes, original-24 counts, cost, needs_review, blocked claims, calls, nudges, p50/p95, totals). Rendering reads only `data.json`.","",
"Rules: pass counts = `eval gate (live): ... n/m` / `pass|FAIL` lines of stdout.txt; cost = sum of `model_call.cost_micro_usd` in stderr.jsonl (cost_source=cost_in_usd_ticks, equal to report.json cost_micro_usd); p50/p95 = recomputed from `model_call.latency_us` (linear interpolation, LLM calls only; report.json p95 differs slightly by method); needs_review = count of `run_needs_review` events; blocked claims = `tool_rejected_by_validation` with code=false_refund_claim; nudges = `completion_nudge` events; happy misses = FAIL lines with category happy among the original 24.","",
"| On screen | Value | Source |","|---|---|---|"]
sha={"v1":"3cbf6a7","v2":"26155b5","v3":"684d7b7"}
for r in R:
    v=f"sources/{r['ver']}/run{r['run']}"
    L.append(f"| {r['ver']} run {r['run']} pass | {r['passed']}/{r['total']} (original 24: {r['orig_passed']}/24) | {v}/stdout.txt, report.json; REPORT.md ({sha[r['ver']]}) |")
    L.append(f"| {r['ver']} run {r['run']} cost US$ | {r['cost_usd']:.4f} ({r['cost_usd']:.6f}) | {v}/stderr.jsonl sum of model_call.cost_micro_usd = report.json cost_micro_usd |")
    L.append(f"| {r['ver']} run {r['run']} LLM p50 / p95 s | {r['p50']:.2f} / {r['p95']:.2f} | {v}/stderr.jsonl latency_us (recomputed) |")
    L.append(f"| {r['ver']} run {r['run']} needs_review / blocked email claims / nudges / happy misses | {r['needs_review']} / {r['claims_blocked']} / {r['nudges']} / {r['happy_miss']} | {v}/stderr.jsonl events; stdout.txt FAIL lines |")
s=d["orig_sums"]; tp=d["totpass"]
L+=[f"| Original 24 cases, sum of 3 runs | v1 {s['v1']}/72, v2 {s['v2']}/72, v3 {s['v3']}/72 (narrated: sixty-two, sixty-six, sixty-seven of seventy-two) | sum of per-run original-24 passes; matches REPORT.md v3 comparison table |",
f"| All cases, 3 runs | v2 {tp['v2']}/81, v3 {tp['v3']}/81 (narrated: seventy-five vs seventy-six of eighty-one) | sum of run passes (26+23+26, 25+25+26) |",
f"| Happy-path misses 4 -> 0 | v1 {d['happy_miss']['v1']}, v2 {d['happy_miss']['v2']}, v3 {d['happy_miss']['v3']} | FAIL lines with category happy in stdout.txt (original 8 happy cases); v1 REPORT: 8/8, 7/8, 5/8 |",
f"| needs_review 2,1,4 -> 1,0,0 -> 0,0,0 | per run, see rows above | run_needs_review events |",
f"| Nudges 21 = {d['nudge_breakdown']['v2_refund_completed']} refund_completed + {d['nudge_breakdown']['v2_needs_ops']} needs_ops (v2) | 6+7+8 | v2 stderr.jsonl completion_nudge fields outcome/reason; v3: {d['nudge_breakdown']['v3_refund_completed']} refund_completed, {d['nudge_breakdown']['v3_needs_ops']} needs_ops |",
f"| Per-case pass counts (12 changed cases) | see table below | per-run `pass|FAIL <case>` lines of stdout.txt; the other 12 original cases were 3/3 in all sets (asserted) |",
f"| Cost per set | v1 {d['tot_cost']['v1']:.4f}, v2 {d['tot_cost']['v2']:.4f}, v3 {d['tot_cost']['v3']:.4f} US$ | sums; equals REPORT.md totals 0.127604 / 0.198092 / 0.164927 |",
f"| Narration: cost per run 'three to eight cents' | 0.0329 to 0.0813 | min/max of the nine run costs |",
f"| Narration: median latency 'point seven to point nine seconds' | 0.70 to 0.90 | min/max of nine p50 values |",
f"| 788 model calls, 9 live runs | {sum(r['calls'] for r in R)} | sum of model_call events |",
"| edge_human_reject loop (needs_review in 1 run, max_steps in 2) | v2 runs 1, 2, 3 | sources/v2/REPORT.md ('Why each case failed') + stderr.jsonl run_needs_review / run_failed counts (v2 run_needs_review 1/0/0; run_failed events 0/2/1, where run 2 also includes adv_other_order, per REPORT) |",
"| 4200-cent refund for a 0-cent request (v2 run 2, edge_zero_amount) | 4200 | sources/v2/run2/stdout.txt line `refund_above_request 4200`; cassette sources/v2/run2_edge_zero_amount_cassette.json (send_refund amount_cents 4200 after the nudge) |",
"| edge_already_refunded: refund_rejected vs expected denied | 0/3 in v3 | sources/v3/run*/stdout.txt (`deterministic outcome expected=denied actual=refund_rejected`); cause not isolated (REPORT v3) |",
"| edge_malformed_id: max_steps loop / invented id | 1/3 in v3 | sources/v3/REPORT.md; run 1 stdout `error=max_steps` |",
"| PR #9, PR #10 | titles | sources/v2/REPORT.md ('Add completion nudge guard and reason/email guards (#9)'), sources/v3/REPORT.md ('Limit completion nudge to unrejected refund_completed claims (#10)') |",
"| 'Noise seen earlier: 1 to 2 cases per run' | 1-2 | sources/v3/REPORT.md comparison header ('noise ~1-2 cases per run') |","",
"## Per-case pass counts (out of 3)","","| case | v1 | v2 | v3 |","|---|---|---|---|"]
for c in d["changed"]: L.append(f"| {c} | {C[c]['v1']} | {C[c]['v2']} | {C[c]['v3']} |")
L+=["","## Not on screen / limits","3 runs per set, one model (grok-4.20-0309-non-reasoning), one prompt per version; case set changed from 24 to 27 between v1 and v2 (comparison uses the original 24). Cause of edge_already_refunded drift not isolated. No business/ROI panel in this version."]
open("number_trace.md","w").write("\n".join(L)); print(len(L))
