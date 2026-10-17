"""Run the golden set against cassettes, or against the live stub when recording.

Each case gets a fresh database. Cases must not see each other's refunds.
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from agent_runtime import __version__
from agent_runtime.catalog import OrderCatalog
from agent_runtime.config import Config
from agent_runtime.evalkit.cases import EvalCase, dump_cassette, load_cases, load_cassette
from agent_runtime.evalkit.judge import judge
from agent_runtime.gate import EXTERNAL_EFFECT_TOOLS
from agent_runtime.jsonutil import as_dict, as_str, loads
from agent_runtime.pricing import MODEL_NAME
from agent_runtime.providers.cassette import CassetteProvider
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.runner import AgentRunner
from agent_runtime.store import SQLiteStore
from agent_runtime.tools import ToolService
from agent_runtime.types import Completion, CompletionRequest, RunOutcome, StepRecord

_CATEGORY_ORDER = ("happy", "edge", "adversarial")


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    deterministic_failures: list[str]
    judge_score: float
    judge_failures: list[str]
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int
    latency_us: list[int]
    tools: list[str]


@dataclass
class SuiteReport:
    ok: bool
    total: int
    passed: int
    failed: int
    tokens_in: int
    tokens_out: int
    cost_micro_usd: int
    latency_us_p50: int
    latency_us_p95: int
    judge_mean: float
    judge_threshold: float
    by_category: dict[str, dict[str, int]]
    results: list[CaseResult]
    text: str


class RecordingProvider:
    """Copies every stub completion so `record` can freeze it."""

    name = "fake"

    def __init__(self) -> None:
        self._inner = FakeProvider()
        self.completions: list[Completion] = []

    def complete(self, request: CompletionRequest) -> Completion:
        completion = self._inner.complete(request)
        self.completions.append(completion)
        return completion


def run_suite(
    evals_dir: Path, threshold: float | None = None, work_dir: Path | None = None
) -> SuiteReport:
    cases = load_cases(evals_dir / "cases.json")
    config = _base_config(evals_dir, threshold)
    results: list[CaseResult] = []
    with _workspace(work_dir) as work:
        for case in cases:
            cassette = load_cassette(evals_dir / "cassettes" / f"{case.id}.json")
            results.append(_run_case(case, CassetteProvider(cassette), config, work))
    return _report(results, config.judge_threshold, "cassette replay")


def record_cassettes(evals_dir: Path, work_dir: Path | None = None) -> None:
    cases = load_cases(evals_dir / "cases.json")
    config = _base_config(evals_dir, None)
    destination = evals_dir / "cassettes"
    destination.mkdir(parents=True, exist_ok=True)
    with _workspace(work_dir) as work:
        for case in cases:
            provider = RecordingProvider()
            _run_case(case, provider, config, work)
            text = dump_cassette(case.id, tuple(provider.completions))
            (destination / f"{case.id}.json").write_text(text + "\n", encoding="utf-8")


def run_regression(evals_dir: Path, work_dir: Path | None = None) -> SuiteReport:
    """Replay one known-bad model transcript through the same gate as CI."""

    payload = as_dict(
        loads((evals_dir / "regressions" / "skip_lookup.json").read_text(encoding="utf-8"))
    )
    case_id = as_str(payload.get("case_id"), "case_id")
    cases = {case.id: case for case in load_cases(evals_dir / "cases.json")}
    case = cases[case_id]
    cassette = load_cassette(evals_dir / "regressions" / "skip_lookup.json")
    config = _base_config(evals_dir, None)
    with _workspace(work_dir) as work:
        result = _run_case(case, CassetteProvider(cassette), config, work)
    report = _report([result], config.judge_threshold, "forced regression")
    why = payload.get("why")
    if isinstance(why, str):
        report.text = f"{why}\n{report.text}"
    return report


def write_report(report: SuiteReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "by_category": report.by_category,
        "cost_micro_usd": report.cost_micro_usd,
        "failed": report.failed,
        "judge_mean": report.judge_mean,
        "judge_threshold": report.judge_threshold,
        "latency_us_p50": report.latency_us_p50,
        "latency_us_p95": report.latency_us_p95,
        "measured_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": MODEL_NAME,
        "passed": report.passed,
        "provider": "cassette",
        "tokens_in": report.tokens_in,
        "tokens_out": report.tokens_out,
        "total": report.total,
        "version": __version__,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_case(
    case: EvalCase,
    provider: CassetteProvider | RecordingProvider,
    config: Config,
    work: Path,
) -> CaseResult:
    case_dir = work / case.id
    case_config = replace(
        config,
        database_path=case_dir / "runtime.sqlite",
        trace_dir=case_dir / "traces",
    )
    store = SQLiteStore(case_config.database_path)
    runner = AgentRunner(case_config, store, provider, ToolService(OrderCatalog(), store))
    outcome, gated = _drive(runner, case.case_input)
    steps = store.list_steps(outcome.run_id)
    tools = [step.name for step in steps if step.kind == "tool"]
    failures = _deterministic(case, outcome, steps, gated, store)
    judgement = judge(case, outcome, steps, gated)
    if judgement.score < config.judge_threshold:
        passed = False
    else:
        passed = not failures
    return CaseResult(
        case_id=case.id,
        category=case.category,
        passed=passed,
        deterministic_failures=failures,
        judge_score=judgement.score,
        judge_failures=list(judgement.failures),
        tokens_in=outcome.tokens_in,
        tokens_out=outcome.tokens_out,
        cost_micro_usd=outcome.spent_micro_usd,
        latency_us=[step.latency_us for step in steps if step.latency_us is not None],
        tools=tools,
    )


def _drive(runner: AgentRunner, payload: dict[str, object]) -> tuple[RunOutcome, list[str]]:
    gated: list[str] = []
    outcome = runner.start(payload)
    # Eight is above the longest happy path (two gates) and stops a loop.
    for _ in range(8):
        if outcome.status != "waiting_review" or not outcome.pending:
            break
        for pending in outcome.pending:
            gated.append(pending.tool_name)
            runner.decide(outcome.run_id, pending.step_id, "approve")
        outcome = runner.resume(outcome.run_id)
    return outcome, gated


def _deterministic(
    case: EvalCase,
    outcome: RunOutcome,
    steps: list[StepRecord],
    gated: list[str],
    store: SQLiteStore,
) -> list[str]:
    failures: list[str] = []
    tools = [step.name for step in steps if step.kind == "tool"]
    if tuple(tools) != case.tools:
        failures.append(f"tool_trajectory expected={list(case.tools)} actual={tools}")
    if outcome.status != "completed":
        failures.append(
            f"run_status expected=completed actual={outcome.status} error={outcome.error}"
        )
    elif outcome.output is None:
        failures.append("final_schema missing")
    else:
        if outcome.output.get("outcome") != case.outcome:
            failures.append(
                f"outcome expected={case.outcome} actual={outcome.output.get('outcome')}"
            )
        actual_amount = outcome.output.get("amount_cents")
        if actual_amount != case.amount_cents:
            failures.append(f"amount_cents expected={case.amount_cents} actual={actual_amount}")
        summary = outcome.output.get("customer_summary")
        if not isinstance(summary, str) or not summary.strip():
            failures.append("final_schema customer_summary")
    refunds = store.count_effects("send_refund")
    emails = store.count_effects("send_email")
    if refunds != case.refund_effects:
        failures.append(f"refund_effects expected={case.refund_effects} actual={refunds}")
    if emails != case.email_effects:
        failures.append(f"email_effects expected={case.email_effects} actual={emails}")
    for name in case.requires_human_gate:
        if name not in gated:
            failures.append(f"missing_gate {name}")
    for step in steps:
        if (
            step.kind == "tool"
            and step.name in EXTERNAL_EFFECT_TOOLS
            and step.status == "succeeded"
        ):
            if step.name not in gated:
                failures.append(f"ungated_effect {step.name}")
    return failures


def _report(results: list[CaseResult], threshold: float, label: str) -> SuiteReport:
    passed = sum(1 for result in results if result.passed)
    total = len(results)
    tokens_in = sum(result.tokens_in for result in results)
    tokens_out = sum(result.tokens_out for result in results)
    cost = sum(result.cost_micro_usd for result in results)
    latencies = [value for result in results for value in result.latency_us]
    scores = [result.judge_score for result in results]
    mean = sum(scores) / len(scores) if scores else 0.0
    by_category: dict[str, dict[str, int]] = {}
    for category in _CATEGORY_ORDER:
        group = [result for result in results if result.category == category]
        by_category[category] = {
            "passed": sum(1 for result in group if result.passed),
            "total": len(group),
        }
    ok = passed == total and total > 0
    lines = [
        (
            f"eval gate ({label}): {'PASS' if ok else 'FAIL'} {passed}/{total} "
            f"judge_mean={mean:.2f} threshold={threshold:.2f}"
        ),
        (
            f"tokens_in={tokens_in} tokens_out={tokens_out} cost_micro_usd={cost} "
            f"latency_us_p50={_percentile(latencies, 50)} "
            f"latency_us_p95={_percentile(latencies, 95)}"
        ),
    ]
    for result in results:
        flag = "pass" if result.passed else "FAIL"
        lines.append(f"{flag} {result.case_id} {result.category} judge={result.judge_score:.2f}")
        for failure in result.deterministic_failures:
            lines.append(f"  deterministic {failure}")
        for failure in result.judge_failures:
            lines.append(f"  judge {failure}")
    return SuiteReport(
        ok=ok,
        total=total,
        passed=passed,
        failed=total - passed,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_micro_usd=cost,
        latency_us_p50=_percentile(latencies, 50),
        latency_us_p95=_percentile(latencies, 95),
        judge_mean=mean,
        judge_threshold=threshold,
        by_category=by_category,
        results=results,
        text="\n".join(lines),
    )


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _base_config(evals_dir: Path, threshold: float | None) -> Config:
    config = Config.from_env({})
    if threshold is None:
        threshold = config.judge_threshold
    return replace(config, evals_dir=evals_dir, judge_threshold=threshold, retry_backoff_ms=0)


class _workspace:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self._path is not None:
            self._path.mkdir(parents=True, exist_ok=True)
            return self._path
        self._temporary = tempfile.TemporaryDirectory(prefix="agent-eval-")
        return Path(self._temporary.name)

    def __exit__(self, *exc: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
