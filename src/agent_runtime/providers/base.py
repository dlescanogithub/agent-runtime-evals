"""The only method the runner needs from a model."""

from __future__ import annotations

from typing import Protocol

from agent_runtime.types import Completion, CompletionRequest


class LLMProvider(Protocol):
    name: str

    def complete(self, request: CompletionRequest) -> Completion:
        """Return the next assistant turn. Raise TransientError to retry."""
