# agent-runtime-evals dashboard demo v2 (three measured re-runs): script used

Voice: xAI TTS `leo` en-US, speed 0.95. Burned-in English subtitles. The mp4 still carries the original Spanish soft track (mov_text, disabled by default). The binary was not re-encoded. The sidecar `agent_runtime_evals_dashboard_demo_en_v2.es.srt` is English and matches the `.en.srt` file. Dashboard canvas rendered with PIL (2560x1240) with camera moves and highlights; code, data and number trace in `evidence/`.

| Start (s) | Segment | Narration |
|---|---|---|
| 0.5 | S0_overview | Three measured re-runs of agent-runtime-evals on main. Three runs each, one model, one prompt. |
| 8.59 | S1_pass | Pass per run: twenty-one, twenty-one, twenty. Then twenty-six, twenty-three, twenty-six. Then twenty-five, twenty-five, twenty-six. Original twenty-four cases: sixty-two, sixty-six, sixty-seven of seventy-two. |
| 25.42 | S2_failure | The failure found: a refund claimed without a confirmed write. Sent to review: two, one, four runs. Four happy-path misses in three runs. |
| 36.54 | S3_control | The control added: a completion guard, pull request nine, that nudges the model to call send refund. Happy-path misses fell to zero. |
| 46.64 | S4_regress | The regression: the human-reject case went from three of three to zero of three. The guard kept asking for a refund the human gate had rejected. |
| 57.08 | S5_fix | The fix, pull request ten, brought it back to three of three. Needs review is zero in all three runs. |
| 64.82 | S6_open | Open: the already-refunded case fell to zero of three, a label mismatch. The malformed-id case passed one of three. Overall, seventy-five versus seventy-six of eighty-one. |
| 78.63 | S7_cost | Cost per run: three to eight cents. Median latency: point seven to point nine seconds. |
| 86.04 | S8_close | Not a clean improvement. Three runs, one model, one prompt. A pilot would tell more. |

Every number is traced in `evidence/number_trace.md`. No business/[EST] panel in this version.
