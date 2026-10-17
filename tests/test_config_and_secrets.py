from pathlib import Path

import pytest

from agent_runtime.config import Config
from agent_runtime.errors import ConfigError
from agent_runtime.secretscan import scan_repo, scan_text


def test_openai_without_a_key_is_rejected() -> None:
    with pytest.raises(ConfigError):
        Config.from_env({"LLM_PROVIDER": "openai"})


def test_secret_scanner_flags_a_sample_and_the_repo_is_clean() -> None:
    sample = "sk-" + ("a" * 24)
    assert "openai_key" in scan_text(sample)
    assert scan_repo(Path(".")) == []
