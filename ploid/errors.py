"""Typed errors mapped from Ploid's PublicApiError shape."""
from __future__ import annotations

from typing import Any, List, Optional


class PloidError(Exception):
    """Base class for every error raised by this SDK."""


class TransportError(PloidError):
    """Network-level failure (DNS, TLS, timeout) before any HTTP response."""


class APIError(PloidError):
    """An error response from the Ploid API.

    Attributes mirror the PublicApiError body:
    ``{"error": {"code", "message", "request_id", "http_status"?,
    "retryable"?, "unavailable_fields"?}}``.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        request_id: Optional[str] = None,
        retryable: Optional[bool] = None,
        unavailable_fields: Optional[List[str]] = None,
        retry_after: Optional[float] = None,
        body: Any = None,
    ) -> None:
        super().__init__(f"[{status}] {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retryable = retryable
        self.unavailable_fields = unavailable_fields or []
        self.retry_after = retry_after
        self.body = body


class ValidationError(APIError):
    """400 / 422 - the request body or parameters were rejected."""


class AuthenticationError(APIError):
    """401 - missing, invalid or revoked credentials."""


class PaymentRequiredError(APIError):
    """402 - the workspace is out of credits or the plan does not cover this."""


class PermissionDeniedError(APIError):
    """403 - the key lacks the scope or plan feature for this operation."""


class NotFoundError(APIError):
    """404 - the resource does not exist."""


class ConflictError(APIError):
    """409 - conflicting state (for example a duplicate or stale write)."""


class GoneError(APIError):
    """410 - the resource existed but is gone (for example an expired run)."""


class PayloadTooLargeError(APIError):
    """413 - the request payload exceeded the limit."""


class RateLimitError(APIError):
    """429 - per-minute rate limit exceeded; ``retry_after`` is set when sent."""


class ServerError(APIError):
    """5xx - a server-side failure; safe to retry idempotent requests."""


_STATUS_MAP = {
    400: ValidationError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    410: GoneError,
    413: PayloadTooLargeError,
    422: ValidationError,
    429: RateLimitError,
}


def error_from_response(status: int, body: Any, retry_after: Optional[float] = None) -> APIError:
    """Build the typed error for an HTTP status + parsed PublicApiError body."""
    code, message, request_id = "unknown_error", f"HTTP {status}", None
    retryable, unavailable = None, []
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        code = str(err.get("code") or code)
        message = str(err.get("message") or message)
        request_id = err.get("request_id")
        retryable = err.get("retryable")
        unavailable = err.get("unavailable_fields") or []
        semantic = err.get("http_status")
        if isinstance(semantic, int) and 400 <= semantic <= 599:
            status = semantic
    cls = _STATUS_MAP.get(status, ServerError if status >= 500 else APIError)
    return cls(
        status,
        code,
        message,
        request_id=request_id,
        retryable=retryable,
        unavailable_fields=unavailable,
        retry_after=retry_after,
        body=body,
    )
