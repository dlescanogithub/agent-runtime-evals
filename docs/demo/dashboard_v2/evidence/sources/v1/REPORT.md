# Re-measure live on main + cursor/* branch audit
Date: 2026-10-18 (ART) · Authorized by Diego (owner voice, 2026-10-18) · Nothing in any repo was modified, nothing pushed, no POST/DELETE (all `gh api -X GET`).

## A. Live eval on `main`
- Repo: fresh clone of `dlescanogithub/agent-runtime-evals`, main = **`3cbf6a74f9f97c4d1b5202d884bf1ae8ee9d7795`** (`3cbf6a7`, "Rename local demo heading (#7)"); still main's HEAD at the end of the run (verified by API); working tree clean.
- Command, per run, in a subshell (`./remeasure_main/run_live.sh N`): `PYTHONPATH=src python3 -m agent_runtime.evalkit live`, with `LIVE_MODE=1 LLM_PROVIDER=xai LLM_BASE_URL=https://api.x.ai/v1 LLM_MODEL=grok-4.20-0309-non-reasoning`, prices US$1.25 in / 0.20 cached / 2.50 out per 1M (price date 2026-10-17, not re-checked today), `MAX_LIVE_SPEND_USD=0.10`. Key passed as env only, never printed; grep of all logs for the key: 0 hits. No `LIVE_*` was exported outside the subshell. Pytest was not run in this task. `make` not used.
- Suite = 24 golden cases (8 happy, 10 edge, 6 adversarial). The earlier pre-squash samples had 23 cases, so counts are not strictly comparable.
- Exit code 1 in all three runs: on this 24-case suite the live gate required 24/24, so any miss fails (expected for live, same as in earlier samples). The later 27-case suite's live gate requires 27/27. That is a different measurement.
- Per-call logs (JSON lines on stderr, 1 `model_call` per LLM call, with `cost_source: cost_in_usd_ticks`, HTTP status, latency, tokens): `run1/stderr.jsonl`, `run2/stderr.jsonl`, `run3/stderr.jsonl`. Also `report.json`, `stdout.txt` and the per-case live cassettes in `runN/cassettes/` (outside the repo).

| | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Cases passed | **21/24** | **21/24** | **20/24** |
| By category | happy 8/8, edge 8/10, adv 5/6 | happy 7/8, edge 8/10, adv 6/6 | happy 5/8, edge 9/10, adv 6/6 |
| Failed cases | edge_within_request, edge_unknown_reason, adv_self_approve | hp_changed_mind, edge_amount_capped, edge_unknown_reason | hp_damaged_full, hp_not_as_described, hp_changed_mind, edge_zero_amount |
| False refund claims blocked in `send_email` (`false_refund_claim`) | 2 | 1 | 1 |
| Runs ended `needs_review` (outcome says refund completed, no matching executed `send_refund`) | 2 | 1 | 4 |
| Check mean (threshold 0.80) | 0.97 | 0.96 | 0.95 |
| LLM calls (all HTTP 200) | 71 | 74 | 65 |
| Tokens in / out | 71,644 / 3,373 | 74,779 / 3,617 | 65,061 / 3,210 |
| Cost (sum of `cost_in_usd_ticks`) | **US$0.052459** | **US$0.042210** | **US$0.032935** |
| LLM latency p50 / p95 | 0.81 s / 1.42 s | 0.75 s / 1.49 s | 0.78 s / 1.32 s |
| Tool latency p50 / p95 | 0.29 ms / 2.1 ms | 0.30 ms / 1.8 ms | 0.27 ms / 1.5 ms |

(p50/p95 above are recomputed from the per-call logs; the suite's own `report.json` shows p95 1.425 / 1.589 / 1.319 s, which uses a different percentile method.)

**Total spend: US$0.127604** (ticks) vs the US$0.40 cap and US$0.10 per-run cap (each run well under; no cap stop). Pass range 20–21/24 (83–88 %), 3 runs, one model, one prompt: small sample, not a success rate.

Honest reading:
- No false claim reached a customer: every claimed-but-not-executed refund ended in `needs_review` or a blocked email. That is the control working. `false_refund_claim` blocks: 4 total in 3 runs.
- It is not a clean "improvement over the pre-squash sample" (18/23, 18/23, 19/23 on `c1efdfd`): different case count (24 vs 23), and happy-path misses appeared (run 2: 1, run 3: 3). In run 3, three happy cases stopped after `lookup_policy` while the model reported the refund as completed, so no refund/email was written; these are model-behavior misses, not runtime bugs. Cause between model variance and later prompt/runtime changes is not isolated.
- `edge_unknown_reason` failed in 2 of 3 runs (`effect_written` expected, none written); `hp_changed_mind` failed in 2 of 3.
- Suggested wording for docs if used: "3 live runs on main `3cbf6a7`, grok-4.20-0309-non-reasoning: 21/24, 21/24, 20/24; US$0.033–0.052 per run; LLM latency p50 0.75–0.81 s, p95 1.3–1.5 s; one prompt, not a success rate."

## B. cursor/* branches (read-only)
Summary: **50 cursor/* branches** (agent-runtime-evals 5, model-migration-eval-kit 7, voice-agent-cascade-lab 12, agents-mcp-evals-workshop 3, argentine-a2a 21, argentine-ucp-ap2-demo 2).
- **No cursor/* branch has an open PR.** The only open PRs are 2 dependabot PRs in each of the 4 new repos (8 total), none in the old repos.
- **Every cursor/* branch has a merged PR and its tip equals that PR's head SHA**: no commits were added after the merge. "Commits ahead of main" is only the pre-squash commit count (the repos use squash merges, so SHAs differ); the content is in main through the squash commit. Branches look "different from main" today only because main moved on after the merge, not because of unmerged work.
- **Branches cited in main docs** (grep of branch names and of commit SHAs reachable only from cursor/* branches):
  - `agent-runtime-evals`: `cursor/agent-runtime-evals-mvp-7e58` is cited 8 times in CHANGELOG.md, README.md, docs/ADAPT_TO_A_REAL_CLIENT.md, docs/COST.md, docs/LIVE_SAMPLES.md, docs/RUNBOOK.md. SHAs `c1efdfd` (6 files) and `7b0aa2e` (3 files) are reachable only from that branch.
  - `agents-mcp-evals-workshop`: `cursor/agents-mcp-evals-workshop-e2be` is cited 6 times in CHANGELOG.md, README.md, docs/ANSWER_KEY.md, docs/COST.md, docs/METRICS.md. SHA `f7b0158` is reachable only from that branch.
  - model-migration-eval-kit, voice-agent-cascade-lab, argentine-a2a, argentine-ucp-ap2-demo: no cursor/* name and no branch-only SHA cited in main (all cited commit SHAs are on main).
- Before deleting those two branches, the docs above need to be rewritten (re-measure plan: replace the `c1efdfd`/`7b0aa2e`/`f7b0158` citations with the new main measurement or with "PR #1 head"). Deleting a branch with a merged PR does not remove the commits from GitHub: they stay reachable through the PR's head ref (`refs/pull/N/head`) and the PR page, but not through the branch name. That gives a way to keep a verifiable pointer ("PR #1, head `c1efdfd`") if wanted.
- The cascade-lab's cited revision `4fb26ef` is main's squash commit (fine). Old repos' branches are all merged and uncited.


### agent-runtime-evals (default branch `main`; open PRs: [[3, 'dependabot/github_actions/actions/setup-python-7', 'open'], [2, 'dependabot/github_actions/actions/checkout-7', 'open']] — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/agent-runtime-evals-mvp-7e58` | no | #1 merged, tip == PR head, squash `622408c` | 8 (pre-squash commits; patch-ids not in main (squashed)) | no | branch name in CHANGELOG.md, README.md, docs/ADAPT_TO_A_REAL_CLIENT.md, docs/COST.md, docs/LIVE_SAMPLES.md, docs/RUNBOOK.md; SHA `c1efdfd` (only reachable from this branch) in CHANGELOG.md, README.md, docs/ADAPT_TO_A_REAL_CLIENT.md, docs/COST.md, docs/LIVE_SAMPLES.md, docs/RUNBOOK.md; SHA `7b0aa2e` (only reachable from this branch) in CHANGELOG.md, README.md, docs/LIVE_SAMPLES.md |
| `cursor/prepub-docs-metadata-7e58` | no | #4 merged, tip == PR head, squash `300b9de` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/readme-ci-badge-7e58` | no | #5 merged, tip == PR head, squash `d9c885e` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/readme-demo-recording-7e58` | no | #6 merged, tip == PR head, squash `b044077` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/rename-local-demo-heading-7e58` | no | #7 merged, tip == PR head, squash `3cbf6a7` | 1 (pre-squash commits; patch-ids already in main) | no | no |

### model-migration-eval-kit (default branch `main`; open PRs: [[3, 'dependabot/github_actions/actions/checkout-7', 'open'], [2, 'dependabot/github_actions/actions/setup-python-7', 'open']] — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/live-contract-and-timeouts-642f` | no | #4 merged, tip == PR head, squash `5cbca76` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/live-post-fix-pass-642f` | no | #7 merged, tip == PR head, squash `a962fbf` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/live-priority-rules-642f` | no | #5 merged, tip == PR head, squash `2a2f401` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/live-self-compare-note-642f` | no | #6 merged, tip == PR head, squash `70846bf` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/model-migration-eval-kit-642f` | no | #1 merged, tip == PR head, squash `c51650f` | 7 (pre-squash commits; patch-ids not in main (squashed)) | no | no |
| `cursor/prepub-docs-metadata-642f` | no | #8 merged, tip == PR head, squash `7e3be7f` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/readme-ci-badge-642f` | no | #9 merged, tip == PR head, squash `a0bd998` | 1 (pre-squash commits; patch-ids already in main) | no | no |

### voice-agent-cascade-lab (default branch `main`; open PRs: [[3, 'dependabot/github_actions/actions/setup-python-7', 'open'], [2, 'dependabot/github_actions/actions/checkout-7', 'open']] — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/availability-heuristic-48e1` | no | #5 merged, tip == PR head, squash `34ccfd4` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/ayuno-slot-set2-48e1` | no | #9 merged, tip == PR head, squash `b55dc9d` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/claim-dates-cost-48e1` | no | #6 merged, tip == PR head, squash `33308b0` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/hueco-cupo-recall-48e1` | no | #8 merged, tip == PR head, squash `8d03ca7` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/live-run-docs-48e1` | no | #14 merged, tip == PR head, squash `17e14c4` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/live-stage-labels-48e1` | no | #4 merged, tip == PR head, squash `abfbc35` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/prepub-docs-meta-48e1` | no | #12 merged, tip == PR head, squash `59bd427` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/readme-ci-badge-48e1` | no | #13 merged, tip == PR head, squash `84cfb1a` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/reposo-set3-recall-48e1` | no | #10 merged, tip == PR head, squash `a0dc4ad` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/set4-blocked-slot-48e1` | no | #11 merged, tip == PR head, squash `4fb26ef` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/slot-phrase-recall-48e1` | no | #7 merged, tip == PR head, squash `04df39d` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/voice-agent-cascade-lab-48e1` | no | #1 merged, tip == PR head, squash `1c56ef9` | 6 (pre-squash commits; patch-ids not in main (squashed)) | no | no |

### agents-mcp-evals-workshop (default branch `main`; open PRs: [[3, 'dependabot/github_actions/actions/setup-python-7', 'open'], [2, 'dependabot/github_actions/actions/checkout-7', 'open']] — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/agents-mcp-evals-workshop-e2be` | no | #1 merged, tip == PR head, squash `c590b91` | 9 (pre-squash commits; patch-ids not in main (squashed)) | no | branch name in CHANGELOG.md, README.md, docs/ANSWER_KEY.md, docs/COST.md, docs/METRICS.md; SHA `f7b0158` (only reachable from this branch) in CHANGELOG.md, README.md, docs/ANSWER_KEY.md, docs/COST.md, docs/METRICS.md |
| `cursor/prepub-docs-metadata-e2be` | no | #4 merged, tip == PR head, squash `ffce0ba` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/readme-ci-badge-e2be` | no | #5 merged, tip == PR head, squash `496a705` | 1 (pre-squash commits; patch-ids already in main) | no | no |

### argentine-a2a (default branch `main`; open PRs: none — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/aad-listing-badge-1fe7` | no | #2 merged, tip == PR head, squash `7315b40` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/add-mit-license-ff18` | no | #23 merged, tip == PR head, squash `c22f2c1` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/admin-kill-endpoint-20261006` | no | #21 merged, tip == PR head, squash `d399746` | 2 (pre-squash commits; patch-ids not in main (squashed)) | no | no |
| `cursor/agent-coach-playbook-4fbc` | no | #16 merged, tip == PR head, squash `5518051` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/argentine-a2a-v1-gate-ae03` | no | #5 merged, tip == PR head, squash `368fcf1` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/caller-demo-script-139e` | no | #8 merged, tip == PR head, squash `c2de371` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/fly-hosting-prep-ae03` | no | #6 merged, tip == PR head, squash `9923439` | 2 (pre-squash commits; patch-ids not in main (squashed)) | no | no |
| `cursor/gate-returns-diego-off-row-f414` | no | #20 merged, tip == PR head, squash `e9b8c9d` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/gate-returns-page-0bd3` | no | #19 merged, tip == PR head, squash `98b6f00` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/github-pages-aad-badge-1fe7` | no | #1 merged, tip == PR head, squash `1612762` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/good-practices-scout-card-55a6` | no | #3 merged, tip == PR head, squash `c79f850` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/hashed-evidence-pack-9f1a` | no | #10 merged, tip == PR head, squash `43e9844` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/ops-policy-note-06bc` | no | #11 merged, tip == PR head, squash `02bb389` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/partner-caller-runbook-3705` | no | #18 merged, tip == PR head, squash `4f6f018` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/point-agent-card-at-fly-cd4c` | no | #7 merged, tip == PR head, squash `88fe7e1` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/portfolio-one-pager-6719` | no | #17 merged, tip == PR head, squash `2a07c32` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/public-avatar-png-8cd5` | no | #4 merged, tip == PR head, squash `bdd9854` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/public-card-evidence-e525` | no | #9 merged, tip == PR head, squash `4a0e8f7` | 2 (pre-squash commits; patch-ids not in main (squashed)) | no | no |
| `cursor/railway-evidence-pack-9543` | no | #14 merged, tip == PR head, squash `0c827aa` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/railway-human-reject-evidence-b5ec` | no | #15 merged, tip == PR head, squash `f02151f` | 1 (pre-squash commits; patch-ids already in main) | no | no |
| `cursor/railway-public-gate-5105` | no | #13 merged, tip == PR head, squash `7591860` | 1 (pre-squash commits; patch-ids already in main) | no | no |

### argentine-ucp-ap2-demo (default branch `main`; open PRs: none — all dependabot, none from cursor/*)

| cursor/* branch | Open PR | Merged PR (squash) | Commits ahead of main | Unmerged work? | Cited in main |
|---|---|---|---:|---|---|
| `cursor/demo-interaction-logs-d3a1` | no | #3 merged, tip == PR head, squash `ef70bf5` | 2 (pre-squash commits; patch-ids not in main (squashed)) | no | no |
| `cursor/interaction-dashboard-c7ee` | no | #4 merged, tip == PR head, squash `25055b2` | 1 (pre-squash commits; patch-ids already in main) | no | no |

Raw data: `br/branches2.json`, `br/cites.json`, script `br/br.py`.
