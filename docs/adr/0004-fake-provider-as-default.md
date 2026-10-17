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
`OpenAICompatibleProvider` is stdlib HTTP, used only when
`LLM_PROVIDER=openai` and the key is in the environment. Tests inject a
transport. They do not open a socket to a vendor. CI does not set the key.

The system prompt is still sent, so token counts include it. The stub does
not follow the prompt. A real model would. The tools and the gate do not
rely on that.

## Consequences

- The green suite shows the runtime against this stub. It does not show
  that a particular hosted model is safe.
- Pointing the HTTP client at a hosted model is a configuration change.
  It does not update the cassettes, and CI will keep replaying the old
  ones. A live eval is future work.
- The adversarial cassettes are this stub obeying the attack. They show
  the controls stopping that stub. They do not prove a hosted model
  behaves the same way.
