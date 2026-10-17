import argparse
from pathlib import Path

from agent_runtime.config import Config
from agent_runtime.errors import ConfigError
from agent_runtime.evalkit.suite import (
    live_cassette_dir,
    record_cassettes,
    run_live,
    run_regression,
    run_suite,
    write_live_report,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-runtime-eval")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="replay cassettes and fail the process on a regression")
    run.add_argument("--report", type=Path, default=None)
    sub.add_parser("record", help="rewrite cassettes from the fake provider")
    sub.add_parser("regression", help="show the gate blocking a forced bad trajectory")
    sub.add_parser(
        "live",
        help="run the golden set against a hosted model; cassettes go to a separate directory",
    )
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
    if args.command == "live":
        try:
            report = run_live(evals_dir)
        except ConfigError as exc:
            print(exc)
            return 2
        print(report.text)
        config = Config.from_env()
        if config.live is not None:
            write_live_report(
                report,
                live_cassette_dir().parent / "report.json",
                config.live.model,
                config.live.price_date,
            )
        return 0 if report.ok else 1
    report = run_suite(evals_dir)
    print(report.text)
    write_report(report, args.report or evals_dir / "results" / "latest.json")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
