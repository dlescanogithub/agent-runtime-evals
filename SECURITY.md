# Security

This is a local runtime with a human gate. It is not a hosted service.

## Secrets

- No API keys, tokens, or private keys belong in the repo.
- `.env.example` lists variables and leaves `OPENAI_API_KEY` empty.
- The process reads configuration from the environment. The fake provider
  is the default and needs no key.
- CI runs two scanners: `python -m agent_runtime.secretscan` and gitleaks
  8.30.1. Either one failing fails the `secrets` job.

## What the model is not allowed to do

- It has no approve tool.
- It does not choose the idempotency key.
- `send_refund` and `send_email` do not execute until a person decides.
- Arguments are checked first. A bad address, a foreign order id in the
  body, or an amount above 100,000 cents never reaches the queue.
- `send_refund` re-checks the policy at execution time.
- The email recipient must be the address on that order.
- INFO logs and JSONL traces do not include the email or the body.

## The API

`python -m agent_runtime.cli serve` has no authentication. The default bind
is `127.0.0.1`. Do not put it on a public interface. In a deployment, the
customer's identity provider sits in front, and the approver role is the
only one that can call approve and reject.

The SQLite file is the other boundary. Write access to it is write access
to the ledger, including the ability to mark a step approved. Protect the
file the way you would protect a database.

## CI and branch protection

GitHub Actions workflow `.github/workflows/ci.yml` runs five jobs:

| Job | What it runs |
|---|---|
| `lint` | `ruff check`, `ruff format --check` |
| `typecheck` | `mypy` (strict on `agent_runtime`) |
| `test` | `pytest` |
| `eval` | cassette suite, which must pass, and the forced regression, which must fail |
| `secrets` | the Python scanner and gitleaks 8.30.1 |

This repository does not enable branch protection. That is a setting on the
GitHub repository, and turning it on is a human action. Before `main`
accepts merges, require those five job names and at least one review from
someone who did not write the change. Do not allow force-pushes to `main`.

## Dependency pinning

Runtime dependencies: none. Dev tools are pinned in `pyproject.toml`
(`ruff==0.17.1`, `mypy==2.4.0`, `pytest==9.1.1`, `pre-commit==4.7.0`).
The Docker image is `python:3.12-slim`. Actions are pinned to major tags
(`actions/checkout@v4`, `actions/setup-python@v5`). Pinning those tags to
commit SHAs is a reasonable next step, not done here.

## Reporting

This is a portfolio repository, not a production service. There is no
security bounty. If you are reading it as a reviewer, the interesting
question is whether a new tool was added without a gate.
