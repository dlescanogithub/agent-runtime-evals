# Risks

Qualitative on purpose. Probabilities here are not measured rates.

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| The model refunds the wrong amount or the wrong order | Medium | High | Policy re-check inside `send_refund`. Amount is capped. Human gate. Eval trajectory includes lookup before refund. | Person who merges prompts |
| Prompt injection in the customer message | Medium | High | The stub reads the message and obeys a few attacks. Validation, the gate, and the tool checks stop those calls. Six adversarial cases, on this stub only. A hosted model is not in the suite. | Person who merges prompts |
| A retry pays twice | Medium | High | Effect key is derived from the business action. The ledger increments in the same transaction as the effect row. | Operator |
| A crash resumes and pays twice | Medium | High | A step left `running` is retried. The effect row makes the retry a no-op. Tested. | Operator |
| Model change looks fine in a demo and fails on Monday | High | High | CI does not see a model change. It replays cassettes. The forced regression proves the gate can go red. A live, capped run is future work. | Person who merges prompts |
| Cost runs away (loop, long context, retries) | Low in this stub, medium with a live model | Medium | Per-run budget. Circuit breaker after consecutive tool failures. Bounded attempts. | Operator |
| Reviewer rubber-stamps the queue | Medium | High | Pilot metric is "approved without edit" plus a sample of rejections. The product cannot force a person to read. The runbook says the approver is accountable. | Approver |
| API exposed beyond localhost | Low if it stays on localhost, high if someone publishes the port | High | Default bind is `127.0.0.1`. Routes other than `GET /health` require `API_TOKEN`. That bearer token is not the customer's identity provider. | Operator |
| Traces leak email addresses | Medium if payloads are logged | Medium | Traces omit email and body. INFO logs do too. | Operator |
| SQLite becomes the production database by inertia | Medium | Medium | ADR 0001 says Postgres and `SKIP LOCKED` are the production design. The pilot exit does not require that move at 120 requests/day [EST]. | Operator |
| Vendor lock-in | Medium | Medium | The runner depends on a small provider interface. The default implementation is local. | Person who merges prompts |
| "The checker said it was fine" with no human check | Medium | Medium | The CI checker is a checklist in code. It is not an LLM judge. No agreement number is published. A later LLM judge would not replace the deterministic checks. | Person who merges prompts |

## What we will not do when a risk shows up

A failing eval is evidence. The response is to fix the agent or to change
the case in a reviewed commit that explains the new expected behavior.
Deleting or loosening the case to go green is not a mitigation.
