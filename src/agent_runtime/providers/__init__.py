"""Model providers. The runner depends on the protocol, not on a vendor SDK."""

from agent_runtime.config import Config
from agent_runtime.errors import ConfigError
from agent_runtime.providers.anthropic import AnthropicProvider
from agent_runtime.providers.base import LLMProvider
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.providers.http import Transport, UrllibTransport
from agent_runtime.providers.openai_compatible import OpenAICompatibleProvider
from agent_runtime.providers.spend import SpendLedger, process_ledger

__all__ = [
    "AnthropicProvider",
    "FakeProvider",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "UrllibTransport",
    "build_provider",
]


def build_provider(
    config: Config,
    *,
    transport: Transport | None = None,
    ledger: SpendLedger | None = None,
) -> LLMProvider:
    if config.llm_provider == "fake":
        if config.live is not None:
            raise ConfigError("LIVE_MODE=1 is not valid with LLM_PROVIDER=fake")
        return FakeProvider()
    if config.live is None:
        raise ConfigError("LIVE_MODE=1 is required for a hosted provider")
    client = transport if transport is not None else UrllibTransport()
    spend = ledger if ledger is not None else process_ledger(config.live.max_spend_micro_usd)
    if config.llm_provider in ("openai", "xai"):
        return OpenAICompatibleProvider(
            name=config.llm_provider,
            settings=config.live,
            transport=client,
            ledger=spend,
        )
    if config.llm_provider == "anthropic":
        return AnthropicProvider(settings=config.live, transport=client, ledger=spend)
    raise ConfigError("LLM_PROVIDER must be fake, xai, openai, or anthropic")
