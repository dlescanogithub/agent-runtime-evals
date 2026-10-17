"""Customer-facing claims that a refund already happened.

An email or a final summary may say a refund was processed only when an
executed ``send_refund`` matches that order and that amount. A non-positive
amount never matches, because the tool refuses to execute one.

This is a heuristic over a fixed phrase list (English, plus a few Spanish
wordings). It is not a guarantee. A paraphrase or a language that is not
listed still gets through. Negation is a nearby word, not a parse.
"""

from __future__ import annotations

import re

from agent_runtime.errors import ValidationError
from agent_runtime.jsonutil import as_dict, loads
from agent_runtime.types import StepRecord

_CLAIM = re.compile(
    r"(?:refund(?:ed)?|reimbursement).{0,80}?(?:processed|issued|completed|approved)"
    r"|(?:processed|issued|completed|approved).{0,40}?(?:refund|reimbursement)",
    re.IGNORECASE | re.DOTALL,
)
_EXTRA = re.compile(
    r"reembolso\s+(?:procesado|emitido|aprobado|realizado|hecho)"
    r"|ya\s+te\s+devolvimos"
    r"|te\s+devolvimos\s+el\s+dinero"
    r"|se\s+acredit[oó]"
    r"|se\s+(?:proces[oó]|realiz[oó])\s+el\s+reembolso"
    r"|hemos\s+devuelto"
    r"|we(?:'ve| have)\s+sent\s+your\s+money\s+back"
    r"|money\s+(?:has been|was)\s+(?:returned|sent back|refunded)",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:not|no|never|without|cannot|can't|won't|wasn't|isn't|hasn't|haven't|"
    r"didn't|unable|nunca|sin|jam[aá]s)\b",
    re.IGNORECASE,
)
_ZERO_CENTS = re.compile(r"\b(?:0|zero|cero)[\s-]*(?:cents?|centavos)\b", re.IGNORECASE)
_CENTS = re.compile(r"\b(\d+)[\s-]*(?:cents?|centavos)\b", re.IGNORECASE)


def text_claims_refund_done(text: str) -> bool:
    """True when the text tells someone a refund was processed or issued.

    A nearby negation ("no refund was issued", "was not processed") does not
    count. The check is the sentence, not a model judge.
    """

    for pattern in (_CLAIM, _EXTRA):
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 48) : match.end()]
            if _NEGATION.search(window):
                continue
            return True
    return False


def stated_refund_cents(text: str) -> int | None:
    """The amount the text names, including zero. None when it names none."""

    if _ZERO_CENTS.search(text):
        return 0
    match = _CENTS.search(text)
    if match is None:
        return None
    return int(match.group(1))


def refund_effect_matches(steps: list[StepRecord], order_id: str, amount: int | None) -> bool:
    """An executed send_refund for this order. Amount <= 0 never matches."""

    if amount is not None and amount <= 0:
        return False
    for step in steps:
        if step.kind != "tool" or step.name != "send_refund" or not step.output_json:
            continue
        try:
            payload = as_dict(loads(step.output_json))
            wrapper = as_dict(loads(step.input_json))
            arguments = as_dict(wrapper.get("arguments"))
        except ValidationError:
            continue
        if payload.get("ok") is not True:
            continue
        if arguments.get("order_id") != order_id:
            continue
        executed = arguments.get("amount_cents")
        if isinstance(executed, bool) or not isinstance(executed, int) or executed < 1:
            continue
        if amount is None or executed == amount:
            return True
    return False
