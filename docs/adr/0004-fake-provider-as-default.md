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

`LLMProvider` is one method: `complete`. `FakeProvider` never reads
`customer_message`. It looks at tool results and calls `policy.decide`,
which is the same function `send_refund` uses. `CassetteProvider` replays a
frozen list of those completions. `OpenAICompatibleProvider` is stdlib HTTP,
used only when `LLM_PROVIDER=openai` and the key is in the environment.
Tests inject a transport. They do not open a socket to a vendor.

The system prompt is still sent, so token counts include it. The stub does
not follow the prompt. A real model would. The tools and the gate do not
rely on that.

## Consequences

- The green suite shows the runtime and the frozen behavior. It does not
  show that a particular hosted model is safe.
- Swapping in a hosted model is a configuration change plus a cassette
  review, not a rewrite of the loop.
- The stub will not surprise us with a novel tool call. The adversarial
  cases document the safe behavior we want a real model to match. They do
  not prove a real model matches it. That is what a live, capped run is for,
  and this MVP does not include one.
