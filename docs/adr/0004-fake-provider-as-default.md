# ADR 0004 — The default model is a local stub

## Status

Accepted.

## Context

The runtime has to be demonstrable on a laptop and in CI with no secret and
no invoice. A real model is still a thing the design must allow, because
the interview question is "what happens when you swap it".

## Options

1. Require an API key. Rejected. The demo then depends on an account.
2. Hide the model behind a interface, default to a deterministic policy
   engine, and keep a thin HTTP client for an OpenAI-shaped API. Chosen.

## Decision

`LLMProvider` is one method: `complete`. `FakeProvider` reads
`customer_message` and classifies it. Ordinary text follows `policy.decide`,
the same function `send_refund` uses. A few attack phrases are obeyed on
purpose, so the tools and the gate are what stop the bad call.
`CassetteProvider` replays a frozen list of those completions.
`OpenAICompatibleProvider` is stdlib HTTP for an OpenAI-shaped API. xAI and
OpenAI both use it. `AnthropicProvider` is a thin Messages adapter, marked
as such, and it is not the CI provider. A hosted provider starts only when
`LIVE_MODE=1` and the key, base URL, model, price date, prices, and
`MAX_LIVE_SPEND_USD` are in the environment. There is no default host and
no vendor price in the repo. Tests inject a transport or talk to localhost.
They do not open a socket to a vendor. CI does not set the key. Three xAI
runs on 2026-10-18, on main `3cbf6a7`, happened outside CI. They are the
README sample: a small sample, not a success rate, and they do not cover
later edits to this client. An earlier 23-case sample from 2026-10-17 is
labelled separately in `docs/LIVE_SAMPLES.md`.

The system prompt is still sent, so token counts include it. The stub does
not follow the prompt. A real model would. The tools and the gate do not
rely on that.

## Consequences

- The green suite shows the runtime against this stub. It does not show
  that a particular hosted model is safe.
- Pointing the HTTP client at a hosted model is `make eval-live`. It writes
  a separate cassette directory and does not replace the ones CI replays.
- The adversarial gate checks invariants, not the stub's tool list. The
  stub cassettes still obey the attack so the tools are exercised. A live
  run on 2026-10-17 mostly ignored the injection, so those guards were
  barely exercised against that model.
