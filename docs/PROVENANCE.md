# Provenance

Nothing in this repository is copied from an employer or from a client engagement.

A few small utilities are maintained in parallel across the portfolio repositories and kept aligned. They are ordinary project files, not a library release.

| Utility | In this repository | What it does |
|---|---|---|
| Cassette replay | `src/agent_runtime/providers/cassette.py` | Plays back a frozen model transcript so CI does not call a paid API. |
| Invariant checks | `src/agent_runtime/evalkit/checks.py` | Scores a finished run in code, against a fixed checklist. |
| JSON trace | `src/agent_runtime/trace.py` | Writes one JSONL file per run. Email bodies stay out of it. |
| Structured logging | `src/agent_runtime/logging_setup.py` | Writes one JSON object per log line on stderr. |
| Secret scanner | `src/agent_runtime/secretscan.py` | Local pattern scan used by `make lint` and CI. |

What was written for this repository, rather than shared as a utility: the refund policy, the human gate on `send_refund` and `send_email`, the synthetic Lumen Goods catalog, and the golden cases.

## Secret scanner

`src/agent_runtime/secretscan.py` is the copy the other portfolio repositories vendor. Keep that file byte-for-byte identical, including this hash. The finding ids name key shapes. They are not a claim of affiliation with any company.

sha256: a3b48e9b7a413d57bbb6e06ef1e3c3194a4100195a61542ad712a87898851709

Check it with `make check-secretscan`, or with the unit test `test_vendored_file_sha256_matches_provenance`. Both recompute the hash of the file bytes and compare it to the line above. A change to the scanner updates the hash in the same commit.
