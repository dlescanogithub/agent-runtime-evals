"""Which tools are allowed to leave the process.

Read tools run immediately. External tools stop the run until a person
approves or rejects them. The model does not get a tool that approves itself.
That decision is a runtime API, not a prompt instruction.
"""

EXTERNAL_EFFECT_TOOLS: frozenset[str] = frozenset({"send_refund", "send_email"})


def requires_human_gate(tool_name: str) -> bool:
    return tool_name in EXTERNAL_EFFECT_TOOLS
