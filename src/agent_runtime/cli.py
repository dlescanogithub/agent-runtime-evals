"""Command line. `python -m agent_runtime.cli demo` is the interview demo."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agent_runtime.config import Config
from agent_runtime.demo import run_demo
from agent_runtime.errors import AgentRuntimeError, ConfigError
from agent_runtime.jsonutil import as_dict, dumps, loads
from agent_runtime.logging_setup import configure
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.store import SQLiteStore
from agent_runtime.wiring import build_runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="crash, resume, and approve one synthetic refund")
    demo.add_argument("--dir", type=Path, default=Path("var/demo"))

    run = sub.add_parser("run", help="start a run from a JSON file and stop at the first gate")
    run.add_argument("--input", type=Path, required=True)

    sub.add_parser("serve", help="localhost API for approve and reject")

    resume = sub.add_parser("resume", help="continue a run after a crash or a decision")
    resume.add_argument("--run-id", required=True)

    approve = sub.add_parser("approve", help="approve a waiting step and resume")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--step-id", required=True)

    reject = sub.add_parser("reject", help="reject a waiting step and resume")
    reject.add_argument("--run-id", required=True)
    reject.add_argument("--step-id", required=True)
    reject.add_argument("--reason", default="Rejected by the operator.")

    show = sub.add_parser("show", help="print a run and its steps")
    show.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    configure(config.log_level)

    try:
        if args.command == "demo":
            # The story is the point of the demo. JSON logs stay available
            # when LOG_LEVEL is set explicitly.
            if "LOG_LEVEL" not in os.environ:
                configure("WARNING")
            summary = run_demo(args.dir)
            for line in summary.lines:
                print(line)
            return 0 if summary.final_status == "completed" else 1
        if args.command == "serve":
            from agent_runtime.api import serve

            serve(config)
            return 0
        runner = build_runner(
            config, provider=FakeProvider() if config.llm_provider == "fake" else None
        )
        if args.command == "run":
            payload = as_dict(loads(args.input.read_text(encoding="utf-8")))
            outcome = runner.start(payload)
            print(dumps(outcome_dict(outcome)))
            return 0
        if args.command == "resume":
            print(dumps(outcome_dict(runner.resume(args.run_id))))
            return 0
        if args.command == "approve":
            runner.decide(args.run_id, args.step_id, "approve")
            print(dumps(outcome_dict(runner.resume(args.run_id))))
            return 0
        if args.command == "reject":
            runner.decide(args.run_id, args.step_id, "reject", args.reason)
            print(dumps(outcome_dict(runner.resume(args.run_id))))
            return 0
        if args.command == "show":
            _show(config, args.run_id)
            return 0
    except AgentRuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("unknown command", file=sys.stderr)
    return 2


def outcome_dict(outcome: object) -> dict[str, object]:
    from agent_runtime.types import RunOutcome

    if not isinstance(outcome, RunOutcome):
        raise TypeError("expected a run outcome")
    pending: list[object] = []
    for item in outcome.pending:
        pending.append(
            {"step_id": item.step_id, "tool_name": item.tool_name, "arguments": item.arguments}
        )
    return {
        "error": outcome.error,
        "output": outcome.output,
        "pending": pending,
        "run_id": outcome.run_id,
        "spent_micro_usd": outcome.spent_micro_usd,
        "status": outcome.status,
        "tokens_in": outcome.tokens_in,
        "tokens_out": outcome.tokens_out,
    }


def _show(config: Config, run_id: str) -> None:
    store = SQLiteStore(config.database_path)
    run = store.get_run(run_id)
    print(
        f"run {run.id} status={run.status} spent_micro_usd={run.spent_micro_usd} error={run.error}"
    )
    for step in store.list_steps(run_id):
        print(
            f"  {step.seq} {step.kind} {step.name} status={step.status} "
            f"attempt={step.attempt} tokens={step.tokens_in}/{step.tokens_out} "
            f"cost_micro_usd={step.cost_micro_usd}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
