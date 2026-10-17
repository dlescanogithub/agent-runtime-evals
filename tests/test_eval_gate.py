import json
import shutil
from pathlib import Path

from agent_runtime.evalkit.__main__ import main as eval_main
from agent_runtime.evalkit.cases import load_cases, load_cassette
from agent_runtime.evalkit.checks import CHECK_IDS
from agent_runtime.evalkit.suite import record_cassettes, run_regression, run_suite


def test_cassette_suite_passes() -> None:
    report = run_suite(Path("evals"))
    assert report.total == 23
    assert report.ok
    assert report.passed == 23
    assert report.check_mean == 1
    counts = {name: item["total"] for name, item in report.by_category.items()}
    assert counts == {"happy": 8, "edge": 9, "adversarial": 6}


def test_forced_regression_fails_the_gate() -> None:
    report = run_regression(Path("evals"))
    assert report.ok is False
    assert report.passed == 0
    assert "tool_trajectory" in report.text
    assert eval_main(["regression"]) == 1


def test_cassettes_match_the_stub(tmp_path: Path) -> None:
    destination = tmp_path / "evals"
    destination.mkdir()
    shutil.copy(Path("evals/cases.json"), destination / "cases.json")
    record_cassettes(destination)
    for case in load_cases(Path("evals/cases.json")):
        fresh = load_cassette(destination / "cassettes" / f"{case.id}.json")
        frozen = load_cassette(Path("evals/cassettes") / f"{case.id}.json")
        assert fresh == frozen


def test_rubric_ids_match_the_checker() -> None:
    rubric = json.loads(Path("evals/rubric.json").read_text(encoding="utf-8"))
    ids = tuple(item["id"] for item in rubric["checks"])
    assert ids == CHECK_IDS
