"""Small JSON helpers.

json.loads is typed as Any. These wrappers narrow the value before the rest
of the code sees it, which is what lets the package type-check in strict mode.
"""

from __future__ import annotations

import json
from typing import cast

from agent_runtime.errors import ValidationError


def loads(text: str) -> object:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid JSON") from exc
    return cast(object, parsed)


def dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError("expected a JSON object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValidationError("JSON object keys must be strings")
        result[key] = item
    return result


def as_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    return value


def as_int(value: object, field: str) -> int:
    # bool is a subclass of int. A JSON true is not an amount.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    return value


def optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return as_int(value, field)


def as_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be a list")
    return cast(list[object], value)
