"""Find credential-shaped strings in a working tree.

Used by `make lint` and CI, beside gitleaks. Patterns are narrow so the
word "token" in a docstring is not a finding. This file is vendored across
the portfolio repositories. ``docs/PROVENANCE.md`` records its sha256.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Finding ids name a key shape. They are not a claim about any company.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("xai_key", re.compile(r"xai-[A-Za-z0-9_-]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("sk_prefix_key", re.compile(r"sk_[A-Za-z0-9]{20,}")),
    ("bearer_token", re.compile(r"(?<![A-Za-z])Bearer [A-Za-z0-9._~+/-]{20,}")),
)

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "var",
}


def scan_text(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS if pattern.search(text)]


def scan_repo(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in scan_text(text):
            findings.append(f"{path.relative_to(root)}:{name}")
    return findings


def main() -> int:
    findings = scan_repo(Path("."))
    if findings:
        for finding in findings:
            print(finding, file=sys.stderr)
        return 1
    print("secret scan: no findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
