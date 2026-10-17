# ADR 0006 — The tool re-checks the policy

## Status

Accepted.

## Context

The eval gate catches a model that skips `lookup_order`. That protects the
next deploy. It does not protect a request already in flight if the model
asks for a refund the policy does not allow. The reviewer might also
approve a number that became stale while the step waited (the order was
refunded by someone else).

## Options

1. Trust the model once the reviewer approves. Rejected. Approval means
   "this action is allowed", not "execute these bytes blindly if the world
   changed".
2. Silently lower the amount at execution time. Rejected. The reviewer
   would have approved a different number than the one that moves.
3. Re-run `policy.decide` inside `send_refund`. If the amount is not the
   allowed amount, return a denial and write no effect. Chosen.

## Decision

`policy.py` is a pure function. The stub calls it when proposing an amount.
`send_refund` calls it again when executing. The two stay aligned because
there is one function, not two copies of the rules.

The hard cap (100,000 cents) is enforced earlier, at validation, so an
absurd amount never reaches the queue.

## Consequences

- A regression that skips lookup but asks for the policy amount can still
  be a valid payment if a person approves it. The eval blocks that
  regression anyway, because the trajectory is part of "good". Defense in
  depth is not a substitute for the process check, and the process check is
  not a substitute for the tool.
- If the policy table changes, cassettes and expectations are updated in
  the same commit. The tool and the stub change together.
