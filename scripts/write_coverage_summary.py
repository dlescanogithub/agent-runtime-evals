"""Print the coverage percent and append it to the GitHub step summary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    report = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    data = json.loads(report.read_text(encoding="utf-8"))
    totals = data.get("totals")
    if not isinstance(totals, dict):
        print("coverage report has no totals", file=sys.stderr)
        return 1
    percent = totals.get("percent_covered")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        print("coverage report has no percent", file=sys.stderr)
        return 1
    line = f"Test coverage (agent_runtime): {percent:.1f}%"
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
