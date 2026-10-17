"""Model providers. The runner depends on the protocol, not on a vendor SDK."""

from agent_runtime.config import Config
from agent_runtime.errors import ConfigError
from agent_runtime.providers.base import LLMProvider
from agent_runtime.providers.fake import FakeProvider
from agent_runtime.providers.openai_compatible import OpenAICompatibleProvider, UrllibTransport

__all__ = [
    "FakeProvider",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "UrllibTransport",
    "build_provider",
]


def build_provider(config: Config) -> LLMProvider:
    if config.llm_provider == "fake":
        return FakeProvider()
    if config.llm_provider == "openai":
        if config.openai_api_key is None:
            raise ConfigError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAICompatibleProvider(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
            model=config.openai_model,
            timeout_s=config.openai_timeout_s,
            transport=UrllibTransport(),
        )
    raise ConfigError("LLM_PROVIDER must be fake or openai")
