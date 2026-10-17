import argparse
from pathlib import Path

from agent_runtime.config import Config
from agent_runtime.evalkit.suite import record_cassettes, run_regression, run_suite, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-runtime-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="replay cassettes and fail the process on a regression")
    run.add_argument("--report", type=Path, default=None)
    sub.add_parser("record", help="rewrite cassettes from the fake provider")
    sub.add_parser("regression", help="show the gate blocking a forced bad trajectory")
    args = parser.parse_args(argv)
    evals_dir = Config.from_env().evals_dir
    if args.command == "record":
        record_cassettes(evals_dir)
        print(f"recorded cassettes in {evals_dir / 'cassettes'}")
        return 0
    if args.command == "regression":
        report = run_regression(evals_dir)
        print(report.text)
        return 0 if report.ok else 1
    report = run_suite(evals_dir)
    print(report.text)
    write_report(report, args.report or evals_dir / "results" / "latest.json")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
