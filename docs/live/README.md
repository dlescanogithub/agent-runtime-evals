# Live logs, 2026-10-18

Three hosted runs of the 24-case golden set, measured outside CI on main
commit `3cbf6a74f9f97c4d1b5202d884bf1ae8ee9d7795` (squash of PR #7). The
model was `grok-4.20-0309-non-reasoning`. This directory is the raw output.
The reading of it is [../LIVE_SAMPLES.md](../LIVE_SAMPLES.md).

## How these files were produced

The command was:

```bash
PYTHONPATH=src python3 -m agent_runtime.evalkit live
```

The environment for each run was `LIVE_MODE=1`, `LLM_PROVIDER=xai`,
`LLM_BASE_URL=https://api.x.ai/v1`, `LLM_MODEL=grok-4.20-0309-non-reasoning`,
and `MAX_LIVE_SPEND_USD=0.10` for that run. Prices supplied to the process
were US$1.25 input, US$0.20 cached input, and US$2.50 output per million
tokens, dated 2026-10-17. Those rates were not re-validated on 2026-10-18.
They are not fields in the JSON. Each `model_call` records `price_date`
`2026-10-17` and `cost_source` `cost_in_usd_ticks`. The measured date on
`report.json` is 2026-10-18.

The API key stayed in the operator's shell. It is not in these files. CI
does not set `LIVE_MODE`.

## What is in each directory

`run1`, `run2`, and `run3` each contain:

- `stderr.jsonl`: one JSON object per log line. Hosted calls are `message`
  `model_call`, with `http_status`, `latency_us`, token counts, and
  `cost_micro_usd`.
- `report.json`: the suite report written by the live command.
- `stdout.txt`: the printed gate. Each file starts with
  `eval gate (live): FAIL`. The live command exits 1 when the passed count
  is below 24.

`stdout.txt` names a local cassette directory (`<local-run-dir>/...`).
Those cassettes are not in this repository.
