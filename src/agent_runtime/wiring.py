"""Put the process together. Tests and the eval harness build their own."""

from __future__ import annotations

from agent_runtime.catalog import OrderCatalog
from agent_runtime.config import Config
from agent_runtime.providers import build_provider
from agent_runtime.providers.base import LLMProvider
from agent_runtime.runner import AgentRunner
from agent_runtime.store import SQLiteStore
from agent_runtime.tools import ToolService


def build_runner(
    config: Config,
    provider: LLMProvider | None = None,
    catalog: OrderCatalog | None = None,
) -> AgentRunner:
    store = SQLiteStore(config.database_path)
    tools = ToolService(catalog or OrderCatalog(), store)
    resolved = build_provider(config) if provider is None else provider
    return AgentRunner(config, store, resolved, tools)
