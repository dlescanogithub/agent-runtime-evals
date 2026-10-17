# Risks

Qualitative on purpose. Probabilities here are not measured rates.

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| The model refunds the wrong amount or the wrong order | Medium | High | Policy re-check inside `send_refund`. Amount is capped. Human gate. Eval trajectory includes lookup before refund. | Person who merges prompts |
| Prompt injection in the customer message | Medium | High | The stub ignores that field. A real model might not, so validation, the gate, and the tool checks do not depend on the model behaving. Six adversarial cases. | Person who merges prompts |
| A retry pays twice | Medium | High | Effect key is derived from the business action. The ledger increments in the same transaction as the effect row. | Operator |
| A crash resumes and pays twice | Medium | High | A step left `running` is retried. The effect row makes the retry a no-op. Tested. | Operator |
| Model change looks fine in a demo and fails on Monday | High | High | Cassette gate on every pull request. Forced-regression job must fail. | Person who merges prompts |
| Cost runs away (loop, long context, retries) | Low in this stub, medium with a live model | Medium | Per-run budget. Circuit breaker after consecutive tool failures. Bounded attempts. | Operator |
| Reviewer rubber-stamps the queue | Medium | High | Pilot metric is "approved without edit" plus a sample of rejections. The product cannot force a person to read. The runbook says the approver is accountable. | Approver |
| API exposed without authentication | Low if it stays on localhost, high if someone publishes the port | High | Default bind is `127.0.0.1`. No auth in the MVP. Runbook forbids exposing it. | Operator |
| Traces leak email addresses | Medium if payloads are logged | Medium | Traces omit email and body. INFO logs do too. | Operator |
| SQLite becomes the production database by inertia | Medium | Medium | ADR 0001 says Postgres and `SKIP LOCKED` are the production design. The pilot exit does not require that move at 120 requests/day [EST]. | Operator |
| Vendor lock-in | Medium | Medium | The runner depends on a small provider interface. The default implementation is local. | Person who merges prompts |
| "The judge said it was fine" with no human check | High if a live judge is added carelessly | Medium | CI judge is a rubric in code. No agreement number is published. A later LLM judge does not replace the deterministic checks. | Person who merges prompts |

## What we will not do when a risk shows up

A failing eval is evidence. The response is to fix the agent or to change
the case in a reviewed commit that explains the new expected behavior.
Deleting or loosening the case to go green is not a mitigation.
