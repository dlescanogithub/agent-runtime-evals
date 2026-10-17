"""Errors the runner knows how to record. Anything else is a bug."""


class AgentRuntimeError(Exception):
    """Base type for expected failures."""


class ConfigError(AgentRuntimeError):
    """The process was started with an invalid environment."""


class ValidationError(AgentRuntimeError):
    """A tool argument or a model payload failed a check."""


class StoreError(AgentRuntimeError):
    """The run ledger could not be read or written."""


class GateError(AgentRuntimeError):
    """A review decision did not match the step that is waiting."""


class TransientError(AgentRuntimeError):
    """Infrastructure failed in a way that a bounded retry might fix.

    A business denial (policy, human rejection, bad arguments) is not transient.
    Retrying those would repeat a decision that already happened.
    """


class PermanentError(AgentRuntimeError):
    """Do not retry. The call cannot succeed with the same inputs."""


class SpendCapError(PermanentError):
    """The live spend cap was hit. Do not retry, and do not use the completion."""
