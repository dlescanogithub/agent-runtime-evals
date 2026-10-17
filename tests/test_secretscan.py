"""Pattern tests for the vendored secret scanner.

Positive samples are built from pieces so this file never holds a literal key.
The same cases belong in every portfolio repository that vendors the module.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from agent_runtime.secretscan import scan_repo, scan_text


def _piece(*parts: str) -> str:
    return "".join(parts)


def test_xai_prefix() -> None:
    assert "xai_key" in scan_text(_piece("xai-", "a" * 20))
    assert "xai_key" in scan_text(_piece("xai-", "A1_b-" * 4))
    assert scan_text(_piece("xai-", "a" * 19)) == []


def test_openai_prefix_including_proj() -> None:
    assert "openai_key" in scan_text(_piece("sk-", "a" * 20))
    assert "openai_key" in scan_text(_piece("sk-proj-", "b" * 20))
    assert scan_text(_piece("sk-", "a" * 19)) == []
    assert "openai_key" not in scan_text(_piece("sk-ant-", "c" * 20))


def test_anthropic_prefix() -> None:
    sample = _piece("sk-ant-", "c" * 20)
    found = scan_text(sample)
    assert "anthropic_key" in found
    assert "openai_key" not in found
    assert scan_text(_piece("sk-ant-", "c" * 19)) == []


def test_sk_prefix() -> None:
    assert "sk_prefix_key" in scan_text(_piece("sk_", "ab" * 10))
    assert "sk_prefix_key" in scan_text(_piece("sk_", "A1" * 10))
    assert scan_text(_piece("sk_", "a" * 19)) == []
    assert "sk_prefix_key" not in scan_text(_piece("sk-", "a" * 20))


def test_github_prefixes() -> None:
    assert "github_token" in scan_text(_piece("ghp_", "A" * 20))
    assert "github_token" in scan_text(_piece("ghp_", "A" * 36))
    assert "github_token" not in scan_text(_piece("ghp_", "A" * 19))
    assert "github_pat" in scan_text(_piece("github_pat_", "a_" * 10))
    assert "github_pat" not in scan_text(_piece("github_pat_", "a" * 19))


def test_aws_access_key() -> None:
    assert "aws_access_key" in scan_text(_piece("AKIA", "A" * 16))
    assert "aws_access_key" in scan_text(_piece("AKIA", "0" * 16))
    assert scan_text(_piece("AKIA", "A" * 15)) == []
    assert scan_text(_piece("akia", "A" * 16)) == []


def test_bearer_token() -> None:
    assert "bearer_token" in scan_text("Authorization: " + _piece("Bearer ", "a" * 20))
    assert scan_text("Authorization: " + _piece("Bearer ", "a" * 19)) == []
    assert scan_text("Authorization: Bearer") == []
    assert scan_text("Bearer token required") == []


def test_private_key_headers() -> None:
    bare = _piece("-----BEGIN ", "PRIVATE KEY-----")
    rsa = _piece("-----BEGIN RSA ", "PRIVATE KEY-----")
    openssh = _piece("-----BEGIN OPENSSH ", "PRIVATE KEY-----")
    ec = _piece("-----BEGIN EC ", "PRIVATE KEY-----")
    dsa = _piece("-----BEGIN DSA ", "PRIVATE KEY-----")
    assert "private_key" in scan_text(bare)
    assert "private_key" in scan_text(rsa)
    assert "private_key" in scan_text(openssh)
    assert "private_key" in scan_text(ec)
    assert "private_key" in scan_text(dsa)
    assert scan_text(_piece("-----BEGIN ", "PUBLIC KEY-----")) == []
    assert scan_text("PRIVATE KEY") == []


def test_ordinary_words_are_not_findings() -> None:
    assert scan_text("token") == []
    assert scan_text("test-key") == []
    assert scan_text("the prefix sk- appears in documentation") == []
    assert scan_text("API_TOKEN is empty") == []


def test_a_file_with_a_built_sample_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("prefix " + _piece("sk-", "d" * 20) + " suffix", encoding="utf-8")
    findings = scan_repo(tmp_path)
    assert findings == ["notes.txt:openai_key"]


def test_this_repository_is_clean() -> None:
    assert scan_repo(Path(".")) == []


def test_vendored_file_sha256_matches_provenance() -> None:
    source = Path("src/agent_runtime/secretscan.py").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    text = Path("docs/PROVENANCE.md").read_text(encoding="utf-8")
    found = re.search(r"(?m)^sha256: ([0-9a-f]{64})$", text)
    assert found is not None
    assert found.group(1) == digest
