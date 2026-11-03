"""ploid-python - a zero-dependency Python SDK for the Ploid API.

Unofficial community SDK built from Ploid's public OpenAPI 2.0.0 document
(https://api.ploid.com/v1/openapi.json).
"""
from .client import Client
from .errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    GoneError,
    NotFoundError,
    PayloadTooLargeError,
    PaymentRequiredError,
    PermissionDeniedError,
    PloidError,
    RateLimitError,
    ServerError,
    TransportError,
    ValidationError,
)
from .polling import PollTimeout
from ._models import PloidObject
from .sse import SSEEvent, iter_sse

__version__ = "0.1.0"
__all__ = [
    "Client",
    "PloidObject",
    "PollTimeout",
    "SSEEvent",
    "iter_sse",
    "PloidError",
    "APIError",
    "ValidationError",
    "AuthenticationError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "PayloadTooLargeError",
    "RateLimitError",
    "ServerError",
    "TransportError",
]
