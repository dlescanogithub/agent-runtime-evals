"""Keep README numbers tied to a live run and the committed report.

Latency is machine-dependent, so the README quotes the committed
evals/results/latest.json rather than a fresh timing.
"""

import json
from pathlib import Path

from agent_runtime.demo import run_demo
from agent_runtime.evalkit.suite import run_suite


def test_readme_matches_live_suite_and_committed_latency(tmp_path: Path) -> None:
    report = run_suite(Path("evals"), work_dir=tmp_path / "suite")
    saved = json.loads(Path("evals/results/latest.json").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")

    assert saved["tokens_in"] == report.tokens_in
    assert saved["tokens_out"] == report.tokens_out
    assert saved["cost_micro_usd"] == report.cost_micro_usd
    assert saved["passed"] == report.passed == 22
    assert saved["total"] == report.total == 22
    assert f"latency_us_p50={saved['latency_us_p50']}" in readme
    assert f"latency_us_p95={saved['latency_us_p95']}" in readme
    marker = (
        f"eval-measured: passed={saved['passed']}/{saved['total']} "
        f"tokens_in={saved['tokens_in']} tokens_out={saved['tokens_out']} "
        f"cost_micro_usd={saved['cost_micro_usd']} "
        f"latency_us_p50={saved['latency_us_p50']} "
        f"latency_us_p95={saved['latency_us_p95']}"
    )
    assert marker in readme


def test_readme_matches_live_demo(tmp_path: Path) -> None:
    summary = run_demo(tmp_path / "demo")
    readme = Path("README.md").read_text(encoding="utf-8")
    marker = (
        f"demo-measured: tokens_in={summary.tokens_in} "
        f"tokens_out={summary.tokens_out} cost_micro_usd={summary.cost_micro_usd}"
    )
    assert marker in readme
    assert summary.final_status == "completed"
    assert summary.refund_effects == 1
    assert summary.email_effects == 1
    assert summary.saw_interrupt
    assert summary.saw_waiting_review
