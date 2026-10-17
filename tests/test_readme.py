"""Keep README token and cost figures tied to a live run.

Latency is machine-dependent. It is stored on the report and is not
compared here, so `make eval` can rewrite those fields without breaking
pytest.
"""

import json
from pathlib import Path

from agent_runtime.demo import run_demo
from agent_runtime.evalkit.suite import run_suite


def test_readme_matches_live_suite_tokens_not_latency(tmp_path: Path) -> None:
    report = run_suite(Path("evals"), work_dir=tmp_path / "suite")
    saved = json.loads(Path("evals/results/latest.json").read_text(encoding="utf-8"))
    readme = Path("README.md").read_text(encoding="utf-8")

    assert saved["tokens_in"] == report.tokens_in
    assert saved["tokens_out"] == report.tokens_out
    assert saved["cost_micro_usd"] == report.cost_micro_usd
    assert saved["passed"] == report.passed
    assert saved["total"] == report.total
    assert "latency_us_p50" not in _measured_line(readme, "eval-measured:")
    assert "latency_us_p95" not in _measured_line(readme, "eval-measured:")
    marker = (
        f"eval-measured: passed={report.passed}/{report.total} "
        f"tokens_in={report.tokens_in} tokens_out={report.tokens_out} "
        f"cost_micro_usd={report.cost_micro_usd}"
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


def _measured_line(readme: str, prefix: str) -> str:
    for line in readme.splitlines():
        if prefix in line:
            return line
    return ""
