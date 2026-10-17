# ADR 0001 — SQLite now, Postgres with SKIP LOCKED later

## Status

Accepted for the MVP.

## Context

A run has to survive a crash. The next worker has to know which step was in
progress and must not claim the same run as someone else. The production
pattern for that queue is Postgres: `SELECT ... FOR UPDATE SKIP LOCKED`.

This repository is a single-process demo and a CI job. Standing up Postgres
would add an operational dependency the golden set does not need.

## Options

1. Keep the state in the model transcript only. Rejected. A crash loses the
   cursor, and two workers can both "continue" the same refund.
2. Postgres from day one. Rejected for the MVP. Right answer when there is
   more than one worker.
3. SQLite with the same tables a Postgres worker would use. Chosen.

## Decision

`runs`, `steps`, `effects`, and `refund_ledger` live in SQLite. One
connection per operation. The runner reloads the run at the start of every
iteration, so the file is the cursor.

The production design, not implemented here:

- the same columns
- a worker transaction that selects a `running` or `interrupted` run
  `FOR UPDATE SKIP LOCKED`
- the effect log still dedupes on the business key, so two workers that
  somehow both pass the lock still cannot pay twice

## Consequences

- `make demo` and CI need no database server.
- The file is a trust boundary. Anyone who can write it can mark a step
  approved. Production puts the database behind credentials and does not
  ship the file around.
- We do not pretend the MVP has been tested under two concurrent workers.
  The idempotent effect is tested. The row lock is not, because it is not
  here.
