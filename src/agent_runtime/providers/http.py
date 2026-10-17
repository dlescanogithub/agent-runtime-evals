"""Stdlib HTTP for hosted model clients.

Tests pass a fake transport. Nothing in CI opens a socket to a vendor.
"""

from __future__ import annotations

import email.utils
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from agent_runtime.errors import PermanentError, TransientError, ValidationError
from agent_runtime.jsonutil import as_dict, loads

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class HttpResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}


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
                return HttpResponse(status=status, body=raw, headers=_header_map(response.headers))
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read(), headers=_header_map(exc.headers))
        except urllib.error.URLError as exc:
            raise TransientError("model endpoint was unreachable") from exc


def read_json(response: HttpResponse) -> dict[str, object]:
    """Turn a model HTTP response into an object, or an error the runner can record."""

    if response.status in RETRYABLE_STATUS:
        raise TransientError(
            f"model endpoint returned HTTP {response.status}",
            http_status=response.status,
            retry_after_s=retry_after_seconds(response.headers),
        )
    if response.status != 200:
        raise PermanentError(f"model endpoint returned HTTP {response.status}")
    try:
        return as_dict(loads(response.body.decode("utf-8")))
    except (UnicodeDecodeError, ValidationError) as exc:
        raise PermanentError("model endpoint returned invalid JSON") from exc


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Delta-seconds or an HTTP date. None when the header is missing or junk."""

    raw = headers.get("retry-after")
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        seconds = (parsed - datetime.now(UTC)).total_seconds()
    if seconds < 0:
        return 0.0
    return seconds


def _header_map(headers: object) -> dict[str, str]:
    mapping = getattr(headers, "items", None)
    if not callable(mapping):
        return {}
    result: dict[str, str] = {}
    for key, value in mapping():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result
