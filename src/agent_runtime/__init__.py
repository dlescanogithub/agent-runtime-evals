"""Minimal agent runtime for a fictional back-office refund desk.

The package is deliberately small: a typed tool loop, a SQLite run ledger,
a human gate for anything that would leave the process, and an eval gate
that can fail CI. The default model is a local stub so the demo needs no key.
"""

__version__ = "0.1.0"
