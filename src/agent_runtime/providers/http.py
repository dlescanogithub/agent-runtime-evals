"""Stdlib HTTP for hosted model clients.

Tests pass a fake transport. Nothing in CI opens a socket to a vendor.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Protocol

from agent_runtime.errors import PermanentError, TransientError, ValidationError
from agent_runtime.jsonutil import as_dict, loads

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class HttpResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body


class Transport(Protocol):
    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        """Send one POST. Raise TransientError when the network itself fails."""


class UrllibTransport:
    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read()
                status = response.status
                if not isinstance(status, int):
                    raise PermanentError("response status was not an integer")
                return HttpResponse(status=status, body=raw)
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read())
        except urllib.error.URLError as exc:
            raise TransientError("model endpoint was unreachable") from exc


def read_json(response: HttpResponse) -> dict[str, object]:
    """Turn a model HTTP response into an object, or an error the runner can record."""

    if response.status in RETRYABLE_STATUS:
        raise TransientError(f"model endpoint returned HTTP {response.status}")
    if response.status != 200:
        raise PermanentError(f"model endpoint returned HTTP {response.status}")
    try:
        return as_dict(loads(response.body.decode("utf-8")))
    except (UnicodeDecodeError, ValidationError) as exc:
        raise PermanentError("model endpoint returned invalid JSON") from exc
